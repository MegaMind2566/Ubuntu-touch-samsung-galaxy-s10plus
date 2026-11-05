/*
 * Copyright © 2026 UBports Foundation
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU General Public License version 3,
 * as published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 * Authored by: Azkali <a.ffcc7@gmail.com>
 */

#include "hidl_system_power_control.h"
#include "bounded_suspend_binder.h"
#include "src/core/log.h"
#include <cstdlib>
#include <stdexcept>
#include <unistd.h>

namespace {
char const* const log_tag = "HidlSystemPowerControl";
char const* const suspend_iface = "android.system.suspend@1.0::ISystemSuspend";
char const* const suspend_name = "android.system.suspend@1.0::ISystemSuspend/default";
char const* const lock_iface = "android.system.suspend@1.0::IWakeLock";
char const* const control_iface = "android.system.suspend.internal.ISuspendControlServiceInternal";
// Android SDK32 pinned AIDL: first method, no arguments, boolean result.
constexpr guint32 enable_autosuspend_transaction = 1;
using namespace repowerd::suspend_binder;
}

repowerd::HidlSystemPowerControl::HidlSystemPowerControl(std::shared_ptr<Log> const& log)
    : log{log}, sm{nullptr}, remote{nullptr}, client{nullptr},
      wake_lock_remote{nullptr}, wake_lock_client{nullptr}
{
    try {
        if (access("/dev/hwbinder", F_OK)) throw std::runtime_error{"No hwbinder interface"};
        Context context;
        if (!context.available()) throw std::runtime_error{"Binder context already owned"};
        sm = gbinder_servicemanager_new("/dev/hwbinder");
        if (!sm) throw std::runtime_error{"No hwservicemanager"};
        auto found = lookup(context, sm, suspend_name, deadline());
        if (!found->accepted) throw std::runtime_error{"SystemSuspend discovery failed/deadline"};
        remote = gbinder_remote_object_ref(found->object); // own, never an autoreleased lookup result
        client = gbinder_client_new(remote, suspend_iface);
        if (!client || !acquire_wake_lock())
            throw std::runtime_error{"Verified bootstrap wake lock unavailable; activation forbidden"};
        log->logInfo(log_tag, "Verified bootstrap wake lock; activation not attempted");
    } catch (...) {
        cleanup();
        throw;
    }
}

repowerd::HidlSystemPowerControl::~HidlSystemPowerControl()
{
    if (activation != Activation::not_attempted)
        log->logWarning(log_tag, "Backend stopping releases Binder locks; reboot required for rollback");
    cleanup();
}

void repowerd::HidlSystemPowerControl::cleanup()
{
    // Dropping all IWakeLock references releases it by the pinned HAL contract.
    // No false promise of a process-independent lock surviving daemon death.
    if (wake_lock_client) gbinder_client_unref(wake_lock_client);
    if (wake_lock_remote) gbinder_remote_object_unref(wake_lock_remote);
    if (client) gbinder_client_unref(client);
    if (remote) gbinder_remote_object_unref(remote);
    if (sm) gbinder_servicemanager_unref(sm);
    wake_lock_client = nullptr;
    wake_lock_remote = nullptr;
    client = nullptr;
    remote = nullptr;
    sm = nullptr;
}

bool repowerd::HidlSystemPowerControl::acquire_wake_lock()
{
    if (wake_lock_client && wake_lock_remote && !gbinder_remote_object_is_dead(wake_lock_remote))
        return true;
    if (!client || !remote || gbinder_remote_object_is_dead(remote)) return false;
    Context context;
    if (!context.available()) return false;
    auto* request = gbinder_client_new_request(client);
    if (!request) return false;
    GBinderWriter writer;
    gbinder_local_request_init_writer(request, &writer);
    gbinder_writer_append_int32(&writer, 0); // PARTIAL
    gbinder_writer_append_hidl_string(&writer, "repowerd");
    auto result = transact(context, client, 1, request, Reply::wake_lock, deadline());
    gbinder_local_request_unref(request);
    if (!result->accepted) return false;
    auto* lock_client = gbinder_client_new(result->object, lock_iface);
    if (!lock_client) return false;
    if (gbinder_remote_object_is_dead(result->object) || gbinder_remote_object_is_dead(remote)) {
        gbinder_client_unref(lock_client);
        return false;
    }
    if (wake_lock_client) gbinder_client_unref(wake_lock_client);
    if (wake_lock_remote) gbinder_remote_object_unref(wake_lock_remote);
    wake_lock_remote = gbinder_remote_object_ref(result->object);
    wake_lock_client = lock_client;
    return true;
}

bool repowerd::HidlSystemPowerControl::release_wake_lock()
{
    if (!wake_lock_client || !wake_lock_remote || gbinder_remote_object_is_dead(wake_lock_remote))
        return false;
    auto* request = gbinder_client_new_request(wake_lock_client);
    if (!request) return false;
    // IWakeLock.release is oneway. Bound the worker transaction too: a timed
    // out delivery may still release server-side, so retain refs but report UNKNOWN.
    Context context;
    auto result = transact(context, wake_lock_client, 1, request, Reply::release, deadline());
    gbinder_local_request_unref(request);
    if (!result->accepted) return false;
    gbinder_client_unref(wake_lock_client);
    gbinder_remote_object_unref(wake_lock_remote);
    wake_lock_client = nullptr;
    wake_lock_remote = nullptr;
    return true;
}

bool repowerd::HidlSystemPowerControl::activate_autosuspend()
{
    Context context;
    if (!context.available()) return false;
    auto const until = deadline(); // shared budget for discovery and activation
    auto* manager = gbinder_servicemanager_new2("/dev/binder", "aidl3", "aidl4");
    if (!manager) return false;
    auto found = lookup(context, manager, "suspend_control_internal", until);
    gbinder_servicemanager_unref(manager);
    if (!found->accepted || std::chrono::steady_clock::now() >= until
        || !remote || gbinder_remote_object_is_dead(remote)
        || !wake_lock_remote || gbinder_remote_object_is_dead(wake_lock_remote)) return false;
    auto* control = gbinder_client_new(found->object, control_iface);
    if (!control) return false;
    auto* request = gbinder_client_new_request(control);
    bool accepted = false;
    if (request) {
        auto result = transact(context, control, enable_autosuspend_transaction,
                               request, Reply::activation, until);
        accepted = result->accepted && !gbinder_remote_object_is_dead(found->object)
            && !gbinder_remote_object_is_dead(remote)
            && wake_lock_remote && !gbinder_remote_object_is_dead(wake_lock_remote);
        gbinder_local_request_unref(request);
    }
    gbinder_client_unref(control);
    return accepted;
}

void repowerd::HidlSystemPowerControl::allow_automatic_suspend(std::string const& id)
{
    std::lock_guard<std::mutex> lock{suspend_mutex};
    if (!suspend_disallowances.erase(id) || !suspend_disallowances.empty()) return;
    if (activation == Activation::failed) {
        log->logWarning(log_tag, "Activation/inhibition failed; no retry and no guard release");
        return;
    }
    if (!wake_lock_client || !wake_lock_remote || gbinder_remote_object_is_dead(wake_lock_remote)
        || !remote || gbinder_remote_object_is_dead(remote)) {
        activation = Activation::failed;
        log->logWarning(log_tag, "inhibition-unavailable; activation forbidden");
        return;
    }
    if (activation == Activation::not_attempted) {
        // Latch before the mutating call: timeout may have committed server-side.
        activation = Activation::failed;
        if (!activate_autosuspend()) {
            log->logWarning(log_tag, "Activation failed/unknown; existing bootstrap guard retained; reboot required");
            return;
        }
        activation = Activation::enabled;
        log->logInfo(log_tag, "Android autosuspend activation acknowledged under verified guard");
    }
    if (!release_wake_lock()) {
        activation = Activation::failed;
        log->logWarning(log_tag, "Wake-lock release status unknown; refs retained, no retry; reboot required");
    }
}

void repowerd::HidlSystemPowerControl::disallow_automatic_suspend(std::string const& id)
{
    std::lock_guard<std::mutex> lock{suspend_mutex};
    suspend_disallowances.insert(id);
    if (activation == Activation::failed) {
        log->logWarning(log_tag, "inhibition-unavailable: backend latched failed; retaining any existing guard");
        return;
    }
    if (!acquire_wake_lock()) {
        activation = Activation::failed;
        log->logWarning(log_tag, "inhibition-unavailable: wake-lock reacquisition failed; no retry; reboot required");
    }
}

void repowerd::HidlSystemPowerControl::start_processing() {}
repowerd::HandlerRegistration repowerd::HidlSystemPowerControl::register_system_resume_handler(SystemResumeHandler const&) { return {}; }
repowerd::HandlerRegistration repowerd::HidlSystemPowerControl::register_system_allow_suspend_handler(SystemAllowSuspendHandler const&) { return {}; }
repowerd::HandlerRegistration repowerd::HidlSystemPowerControl::register_system_disallow_suspend_handler(SystemDisallowSuspendHandler const&) { return {}; }
void repowerd::HidlSystemPowerControl::power_off() { if (system("shutdown -P now")) {} }
void repowerd::HidlSystemPowerControl::suspend() {}
void repowerd::HidlSystemPowerControl::allow_default_system_handlers() {}
void repowerd::HidlSystemPowerControl::disallow_default_system_handlers() {}
