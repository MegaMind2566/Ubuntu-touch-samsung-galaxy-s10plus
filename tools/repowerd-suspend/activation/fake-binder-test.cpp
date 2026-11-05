// SPDX-License-Identifier: GPL-3.0-only
// Compile the actual adapter and bounded helper against real libgbinder headers,
// replacing only the C transport boundary. No Binder device or power API is used.
#include "src/adapters/hidl_system_power_control.h"
#include "src/core/log.h"
#include <glib.h>
#include <chrono>
#include <cstring>
#include <iostream>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#define REQUIRE(value) do { if (!(value)) throw std::runtime_error(#value); } while (0)
struct gbinder_remote_object { int refs{0}; bool dead{false}; bool wake_lock{false}; bool held{false}; };
struct gbinder_servicemanager { int refs{1}; bool aidl{false}; };
struct gbinder_client { int refs{1}; GBinderRemoteObject* object; std::string iface; };
struct gbinder_local_request { int type{-1}; std::string name; };
struct gbinder_remote_reply { std::vector<gint32> words; GBinderRemoteObject* object{nullptr}; };
struct Job {
    gulong id;
    GBinderClient* client;
    GBinderClientReplyFunc reply;
    GDestroyNotify destroy;
    void* data;
    bool cancelled{false};
    bool activation{false};
    bool release{false};
    int status{0};
    gbinder_remote_reply response;
};
struct Scenario {
    int acquire_count{0}, enable_count{0}, release_count{0}, holders{0};
    int fail_acquire_after{100}, activation_status{0}, release_status{0};
    guint activation_delay{0}, discovery_delay{0}, release_delay{0};
    bool missing_control{false}, server_enabled{false};
    std::vector<gint32> activation_words{0, 1};
    gulong serial{1};
    std::vector<std::unique_ptr<gbinder_remote_object>> objects;
    std::vector<std::unique_ptr<gbinder_client>> clients;
    std::vector<std::unique_ptr<gbinder_servicemanager>> managers;
    std::map<gulong, Job*> jobs;
    GBinderRemoteObject* suspend;
    GBinderRemoteObject* control;
    Scenario() {
        suspend = make_object(false); control = make_object(false);
    }
    GBinderRemoteObject* make_object(bool lock) {
        objects.push_back(std::make_unique<gbinder_remote_object>());
        auto* object = objects.back().get(); object->wake_lock = lock; object->held = lock;
        return object;
    }
    int held() const { int n=0; for (auto const& p: objects) n += p->held; return n; }
    void clean() const {
        REQUIRE(jobs.empty()); REQUIRE(holders == 0); REQUIRE(held() == 0);
        for (auto const& p: objects) REQUIRE(p->refs == 0);
        for (auto const& p: clients) REQUIRE(p->refs == 0);
        for (auto const& p: managers) REQUIRE(p->refs == 0);
    }
};
static Scenario* world;

extern "C" int s10_fake_access(char const*, int) noexcept { return 0; }
extern "C" GBinderRemoteObject* gbinder_remote_object_ref(GBinderRemoteObject* p) { if(p) ++p->refs; return p; }
extern "C" void gbinder_remote_object_unref(GBinderRemoteObject* p) {
    if(p) { REQUIRE(p->refs > 0); if (!--p->refs && p->wake_lock) p->held=false; }
}
extern "C" gboolean gbinder_remote_object_is_dead(GBinderRemoteObject* p) { return !p || p->dead; }
extern "C" GBinderServiceManager* gbinder_servicemanager_new(char const* device) {
    REQUIRE(!strcmp(device,"/dev/hwbinder"));
    world->managers.push_back(std::make_unique<gbinder_servicemanager>());
    return world->managers.back().get();
}
extern "C" GBinderServiceManager* gbinder_servicemanager_new2(char const* device, char const* sm, char const* rpc) {
    REQUIRE(!strcmp(device,"/dev/binder")); REQUIRE(!strcmp(sm,"aidl3")); REQUIRE(!strcmp(rpc,"aidl4"));
    world->managers.push_back(std::make_unique<gbinder_servicemanager>());
    auto* result=world->managers.back().get(); result->aidl=true; return result;
}
extern "C" void gbinder_servicemanager_unref(GBinderServiceManager* p) { if(p) { REQUIRE(p->refs>0); --p->refs; } }
extern "C" gulong gbinder_servicemanager_get_service(GBinderServiceManager* manager, char const* name,
                GBinderServiceManagerGetServiceFunc callback, void* data) {
    REQUIRE(!strcmp(name, manager->aidl ? "suspend_control_internal" : "android.system.suspend@1.0::ISystemSuspend/default"));
    struct Lookup { GBinderServiceManager* manager; GBinderServiceManagerGetServiceFunc callback; void* data; };
    auto* lookup=new Lookup{manager,callback,data}; ++manager->refs;
    ++world->holders;
    g_timeout_add(manager->aidl ? world->discovery_delay : 0, [](void* raw) -> gboolean {
        std::unique_ptr<Lookup> p{static_cast<Lookup*>(raw)};
        auto* object=p->manager->aidl ? world->control : world->suspend;
        if (p->manager->aidl && world->missing_control) object=nullptr;
        gbinder_remote_object_ref(object); // borrowed during callback only
        p->callback(p->manager,object,object ? 0 : -1,p->data);
        gbinder_remote_object_unref(object); gbinder_servicemanager_unref(p->manager);
        --world->holders; return G_SOURCE_REMOVE;
    }, lookup);
    return ++world->serial;
}
extern "C" GBinderClient* gbinder_client_new(GBinderRemoteObject* object, char const* iface) {
    REQUIRE(object && object->refs>0);
    world->clients.push_back(std::make_unique<gbinder_client>());
    auto* p=world->clients.back().get(); p->object=gbinder_remote_object_ref(object); p->iface=iface; return p;
}
extern "C" void gbinder_client_unref(GBinderClient* p) {
    if(p) { REQUIRE(p->refs>0); if (!--p->refs) gbinder_remote_object_unref(p->object); }
}
extern "C" GBinderLocalRequest* gbinder_client_new_request(GBinderClient* p) {
    REQUIRE(p && p->refs>0); return new gbinder_local_request;
}
extern "C" void gbinder_local_request_unref(GBinderLocalRequest* p) { delete p; }
extern "C" void gbinder_local_request_init_writer(GBinderLocalRequest* p, GBinderWriter* w) { w->d[0]=p; }
extern "C" void gbinder_writer_append_int32(GBinderWriter* w, guint32 n) {
    const_cast<gbinder_local_request*>(static_cast<gbinder_local_request const*>(w->d[0]))->type=n;
}
extern "C" void gbinder_writer_append_hidl_string(GBinderWriter* w, char const* text) {
    const_cast<gbinder_local_request*>(static_cast<gbinder_local_request const*>(w->d[0]))->name=text;
}
extern "C" gulong gbinder_client_transact(GBinderClient* client, guint32 code, guint32 flags,
        GBinderLocalRequest* request, GBinderClientReplyFunc reply, GDestroyNotify destroy, void* data) {
    REQUIRE(code==1); REQUIRE(client->refs>0);
    auto* job=new Job{++world->serial,client,reply,destroy,data}; ++client->refs;
    job->activation=client->iface=="android.system.suspend.internal.ISuspendControlServiceInternal";
    job->release=client->iface=="android.system.suspend@1.0::IWakeLock";
    REQUIRE(flags==(job->release ? GBINDER_TX_FLAG_ONEWAY : 0));
    if (job->release) {
        ++world->release_count; job->status=world->release_status;
    } else if (job->activation) {
        REQUIRE(world->held()==1); ++world->enable_count;
        job->response.words=world->activation_words; job->status=world->activation_status;
    } else {
        REQUIRE(client->iface=="android.system.suspend@1.0::ISystemSuspend");
        REQUIRE(request->type==0 && request->name=="repowerd");
        ++world->acquire_count;
        if (world->acquire_count > world->fail_acquire_after) job->response.words={1};
        else {
            job->response.words={0}; job->response.object=world->make_object(true);
            gbinder_remote_object_ref(job->response.object); // reply ownership
        }
    }
    world->jobs[job->id]=job; ++world->holders;
    g_timeout_add(job->activation ? world->activation_delay : job->release ? world->release_delay : 0, [](void* raw) -> gboolean {
        std::unique_ptr<Job> job{static_cast<Job*>(raw)};
        // The server may execute even if client delivery was cancelled.
        if (job->activation && !job->status && job->response.words==std::vector<gint32>{0,1}) world->server_enabled=true;
        if (job->release && !job->status) job->client->object->held=false;
        if (!job->cancelled) job->reply(job->client,job->release ? nullptr : &job->response,job->status,job->data);
        job->destroy(job->data); gbinder_remote_object_unref(job->response.object);
        gbinder_client_unref(job->client); world->jobs.erase(job->id); --world->holders;
        return G_SOURCE_REMOVE;
    },job);
    return job->id;
}
extern "C" void gbinder_client_cancel(GBinderClient*, gulong id) {
    auto it=world->jobs.find(id); if(it!=world->jobs.end()) it->second->cancelled=true;
}
extern "C" int gbinder_client_transact_sync_oneway(GBinderClient* client, guint32 code, GBinderLocalRequest*) {
    REQUIRE(client->iface=="android.system.suspend@1.0::IWakeLock" && code==1);
    ++world->release_count;
    if (!world->release_status) client->object->held=false;
    return world->release_status;
}
extern "C" void gbinder_remote_reply_init_reader(GBinderRemoteReply* reply, GBinderReader* reader) {
    reader->d[0]=reply; reader->d[1]=nullptr;
}
static size_t position(GBinderReader const* reader) { return reinterpret_cast<size_t>(reader->d[1]); }
extern "C" gboolean gbinder_reader_read_int32(GBinderReader* reader, gint32* value) {
    auto* reply=static_cast<gbinder_remote_reply const*>(reader->d[0]); auto const pos=position(reader);
    if(pos>=reply->words.size()) return FALSE;
    if(value) *value=reply->words[pos]; reader->d[1]=reinterpret_cast<void const*>(pos+1); return TRUE;
}
extern "C" GBinderRemoteObject* gbinder_reader_read_object(GBinderReader* reader) {
    auto* reply=static_cast<gbinder_remote_reply const*>(reader->d[0]); auto const pos=position(reader);
    if(pos!=reply->words.size() || !reply->object) return nullptr;
    reader->d[1]=reinterpret_cast<void const*>(pos+1); return gbinder_remote_object_ref(reply->object);
}
extern "C" gboolean gbinder_reader_at_end(GBinderReader const* reader) {
    auto* reply=static_cast<gbinder_remote_reply const*>(reader->d[0]);
    return position(reader)==reply->words.size()+(reply->object ? 1 : 0);
}
struct Log : repowerd::Log {
    std::vector<std::string> messages;
    Log(): repowerd::Log(repowerd::LogLevel::Debug) {}
    void logOutput(repowerd::LogLevel, char const*, char const* format, va_list) override { messages.push_back(format); }
    bool contains(char const* needle) { for(auto const& s:messages) if(s.find(needle)!=std::string::npos) return true; return false; }
};
static void drain(unsigned millis=200) {
    auto until=std::chrono::steady_clock::now()+std::chrono::milliseconds{millis};
    do { while(g_main_context_iteration(nullptr,FALSE)) {} std::this_thread::sleep_for(std::chrono::milliseconds{1}); }
    while(std::chrono::steady_clock::now()<until);
}
int main(int argc,char** argv) {
    REQUIRE(argc==2); std::string test=argv[1]; Scenario scenario; world=&scenario;
    auto log=std::make_shared<Log>();
    if(test=="startup-failure") scenario.fail_acquire_after=0;
    if(test=="false") scenario.activation_words={0,0};
    if(test=="malformed-bool") scenario.activation_words={0,2};
    if(test=="exception") scenario.activation_words={-1,1};
    if(test=="truncated") scenario.activation_words={0};
    if(test=="trailing") scenario.activation_words={0,1,7};
    if(test=="transport-error") scenario.activation_status=-5;
    if(test=="timeout") scenario.activation_delay=3100;
    if(test=="discovery-timeout") scenario.discovery_delay=3100;
    if(test=="missing-service") scenario.missing_control=true;
    if(test=="release-error") scenario.release_status=-5;
    if(test=="release-deadline") scenario.release_delay=3100;
    try {
        {
            repowerd::HidlSystemPowerControl adapter(log);
            REQUIRE(test!="startup-failure"); REQUIRE(scenario.held()==1 && scenario.enable_count==0);
            adapter.allow_automatic_suspend("unknown"); REQUIRE(scenario.enable_count==0 && scenario.held()==1);
            adapter.disallow_automatic_suspend("a"); adapter.disallow_automatic_suspend("b");
            adapter.allow_automatic_suspend("a"); REQUIRE(scenario.enable_count==0 && scenario.held()==1);
            if(test=="service-death") {
                scenario.suspend->dead=true;
                for(auto const& object: scenario.objects) if(object->wake_lock) { object->dead=true; object->held=false; }
            }
            auto start=std::chrono::steady_clock::now(); adapter.allow_automatic_suspend("b");
            auto elapsed=std::chrono::steady_clock::now()-start;
            REQUIRE(elapsed<std::chrono::milliseconds{3200});
            if(test=="success" || test=="reacquire-failure") {
                REQUIRE(scenario.enable_count==1 && scenario.server_enabled && scenario.held()==0);
                if(test=="reacquire-failure") scenario.fail_acquire_after=1;
                adapter.disallow_automatic_suspend("c");
                if(test=="success") REQUIRE(scenario.held()==1);
                else { REQUIRE(scenario.held()==0); REQUIRE(log->contains("inhibition-unavailable")); }
                adapter.allow_automatic_suspend("c"); REQUIRE(scenario.enable_count==1);
                REQUIRE(scenario.held()==0);
            } else {
                REQUIRE(scenario.held()==(test=="service-death" ? 0 : 1));
                auto const attempts=scenario.enable_count;
                adapter.disallow_automatic_suspend("retry"); adapter.allow_automatic_suspend("retry");
                REQUIRE(scenario.enable_count==attempts && scenario.held()==(test=="service-death" ? 0 : 1));
                if(test=="timeout") { drain(200); REQUIRE(scenario.server_enabled && scenario.held()==1); }
                if(test=="release-deadline") { drain(200); REQUIRE(scenario.held()==0 && scenario.release_count==1); REQUIRE(log->contains("unknown")); }
                REQUIRE(log->contains("failed") || log->contains("unknown") || log->contains("unavailable"));
            }
        }
        REQUIRE(test!="startup-failure");
    } catch(std::runtime_error const& error) {
        if(test!="startup-failure") throw;
        REQUIRE(scenario.enable_count==0 && scenario.acquire_count==1);
    }
    drain(200); scenario.clean();
    std::cout<<test<<": passed (actual adapter; fake transport; no power operation)\n";
}
