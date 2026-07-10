import asyncio
from datetime import date
from bson import ObjectId
from config.database import reminders_collection, users_collection
from utils.notifications import send_expo_push_notification

async def send_daily_refill_reminders():
    today_str = date.today().strftime("%Y-%m-%d")
    print(f"[Scheduler] Running refill reminder check for {today_str}...")
    
    # Find all active reminders triggered for today
    cursor = reminders_collection.find({
        "trigger_date": today_str,
        "is_active": True
    })
    
    reminders = await cursor.to_list(length=1000)
    print(f"[Scheduler] Found {len(reminders)} reminders to trigger today.")
    
    sent_count = 0
    for reminder in reminders:
        user_id = reminder["user_id"]
        # Find user to get push token
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            print(f"[Scheduler] User {user_id} not found for reminder {reminder['_id']}.")
            continue
            
        push_token = user.get("expo_push_token")
        if not push_token:
            print(f"[Scheduler] User {user['name']} has no push token. Skipping.")
            continue
            
        medicine_name = reminder["medicine_name"]
        title = "Refill Reminder 💊"
        body = f"Hi {user['name']}, your supply of {medicine_name} is running low! You have about 4 days left."
        
        success = send_expo_push_notification(
            expo_push_token=push_token,
            title=title,
            body=body,
            data={"reminder_id": str(reminder["_id"]), "medicine_id": reminder["medicine_id"]}
        )
        if success:
            sent_count += 1
            
    print(f"[Scheduler] Completed daily check. Sent {sent_count} notifications.")
    return sent_count

def start_reminder_scheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = BackgroundScheduler()
        
        def job_wrapper():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(send_daily_refill_reminders())
            finally:
                loop.close()
            
        scheduler.add_job(
            job_wrapper,
            trigger=CronTrigger(hour=0, minute=0),
            id="refill_reminder_job",
            name="Daily refill reminder push notifications at midnight",
            replace_existing=True
        )
        scheduler.start()
        print("[Scheduler] APScheduler started successfully.")
    except Exception as e:
        print(f"[Scheduler Warning] Failed to start APScheduler ({e}). Starting fallback asyncio task...")
        
        async def fallback_loop():
            # Wait for application to startup fully
            await asyncio.sleep(5)
            while True:
                try:
                    await send_daily_refill_reminders()
                except Exception as ex:
                    print(f"[Scheduler Fallback Error] {ex}")
                # Sleep 24 hours
                await asyncio.sleep(86400)
                
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(fallback_loop())
            print("[Scheduler] Fallback asyncio task spawned successfully.")
        except RuntimeError:
            print("[Scheduler Error] No running event loop to attach fallback task.")
