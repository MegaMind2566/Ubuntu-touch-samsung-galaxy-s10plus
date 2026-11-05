// SPDX-License-Identifier: GPL-3.0-only
// Included by the adapter patch; also compiled unchanged against fake Binder boundaries.
#pragma once
#include <gbinder.h>
#include <atomic>
#include <chrono>
#include <memory>
#include <thread>

namespace repowerd { namespace suspend_binder {
using Deadline = std::chrono::steady_clock::time_point;
inline Deadline deadline() { return std::chrono::steady_clock::now() + std::chrono::seconds{3}; }

// libgbinder 1.1.52 dispatches on the global default context, not a thread-default
// context. Refuse concurrent ownership instead of nesting another daemon's loop.
class Context {
public:
    Context() : context{g_main_context_default()}, owned{g_main_context_acquire(context) != FALSE} {}
    ~Context() { if (owned) g_main_context_release(context); }
    bool available() const { return owned; }
    template<class State> bool wait(std::shared_ptr<State> const& state, Deadline until) {
        while (std::chrono::steady_clock::now() < until) {
            if (state->done.load(std::memory_order_acquire)) return true;
            g_main_context_iteration(context, FALSE);
            if (state->done.load(std::memory_order_acquire))
                return std::chrono::steady_clock::now() < until;
            std::this_thread::sleep_for(std::chrono::milliseconds{1});
        }
        return false;
    }
private:
    GMainContext* context;
    bool owned;
};

struct Result {
    std::atomic<bool> done{false};
    bool accepted{false};
    GBinderRemoteObject* object{nullptr};
    ~Result() { if (object) gbinder_remote_object_unref(object); }
};
using Holder = std::shared_ptr<Result>;

inline Holder lookup(Context& context, GBinderServiceManager* manager,
                     char const* name, Deadline until) {
    auto result = std::make_shared<Result>();
    if (!context.available() || std::chrono::steady_clock::now() >= until) return result;
    auto* holder = new Holder{result};
    auto const id = gbinder_servicemanager_get_service(manager, name,
        [](GBinderServiceManager*, GBinderRemoteObject* object, int status, void* data) {
            std::unique_ptr<Holder> holder{static_cast<Holder*>(data)};
            auto& result = **holder;
            if (!status && object && !gbinder_remote_object_is_dead(object)) {
                result.object = gbinder_remote_object_ref(object); // callback object is borrowed
                result.accepted = true;
            }
            result.done.store(true, std::memory_order_release);
        }, holder);
    if (!id) { delete holder; return result; }
    if (!context.wait(result, until)) result->accepted = false;
    // This API has no userdata destructor. Do not cancel: the eventual callback
    // owns the heap holder. If kernel Binder never returns, at most one holder
    // survives for that lookup until process exit. It never references the adapter.
    return result;
}

enum class Reply { wake_lock, activation, release };
struct RequestState : Result { Reply kind; explicit RequestState(Reply value) : kind{value} {} };
using RequestHolder = std::shared_ptr<RequestState>;

inline RequestHolder transact(Context& context, GBinderClient* client,
                              guint32 code, GBinderLocalRequest* request,
                              Reply kind, Deadline until) {
    auto result = std::make_shared<RequestState>(kind);
    if (!context.available() || std::chrono::steady_clock::now() >= until) return result;
    auto* holder = new RequestHolder{result};
    auto const id = gbinder_client_transact(client, code, kind == Reply::release ? GBINDER_TX_FLAG_ONEWAY : 0, request,
        [](GBinderClient*, GBinderRemoteReply* reply, int status, void* data) {
            auto& result = **static_cast<RequestHolder*>(data);
            if (result.kind == Reply::release) {
                result.accepted = status == 0; // oneway has no reply parcel
            } else if (!status && reply) {
                GBinderReader reader;
                gint32 exception = -1;
                gbinder_remote_reply_init_reader(reply, &reader);
                if (gbinder_reader_read_int32(&reader, &exception) && exception == 0) {
                    if (result.kind == Reply::activation) {
                        gint32 value = 0;
                        result.accepted = gbinder_reader_read_int32(&reader, &value)
                            && value == 1 && gbinder_reader_at_end(&reader);
                    } else {
                        auto* object = gbinder_reader_read_object(&reader); // returns owned reference
                        if (object && !gbinder_remote_object_is_dead(object)
                            && gbinder_reader_at_end(&reader)) {
                            result.object = object;
                            result.accepted = true;
                        } else if (object) gbinder_remote_object_unref(object);
                    }
                }
            }
            result.done.store(true, std::memory_order_release);
        }, [](void* data) { delete static_cast<RequestHolder*>(data); }, holder);
    if (!id) { delete holder; return result; }
    if (!context.wait(result, until)) {
        result->accepted = false;
        // cancel suppresses delivery, not server execution. The deferred destroy
        // callback owns holder; no stack/adapter pointer can become dangling.
        gbinder_client_cancel(client, id);
    }
    return result;
}
}}
