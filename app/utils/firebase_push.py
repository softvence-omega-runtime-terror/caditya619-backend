# # utils/firebase_push.py
# import firebase_admin
# from firebase_admin import messaging
# from applications.user.rider import RiderProfile as Rider
# import logging

# # Initialize once
# if not firebase_admin._apps:
#     firebase_admin.initialize_app(
#         firebase_admin.credentials.Certificate("app/firebase_service_account.json")
#     )

# logger = logging.getLogger(__name__)

# async def send_scheduled_push(rider_id: int, title: str, body: str, data: dict = None):
#     rider = await Rider.get_or_none(id=rider_id)
#     if not rider or not rider.fcm_token:
#         logger.warning(f"Rider {rider_id} has no FCM token")
#         return False

#     message = messaging.Message(
#         notification=messaging.Notification(title=title, body=body),
#         data=data or {},
#         token=rider.fcm_token,
#         android=messaging.AndroidConfig(priority="high"),
#         apns=messaging.APNSConfig(payload=messaging.APNSPayload(
#             aps=messaging.APNSPayload.Aps(sound="default", badge=1)
#         ))
#     )

#     try:
#         response = messaging.send(message)
#         logger.info(f"Push sent to rider {rider_id}: {response}")
#         return True
#     except Exception as e:
#         logger.error(f"Failed to send push to rider {rider_id}: {e}")
#         return False








# utils/firebase_push.py
import asyncio
import logging
import firebase_admin
from firebase_admin import messaging
from applications.user.rider import RiderProfile as Rider

# Initialize once
if not firebase_admin._apps:
    firebase_admin.initialize_app(
        firebase_admin.credentials.Certificate("app/firebase_service_account.json")
    )

logger = logging.getLogger(__name__)


async def send_scheduled_push(rider_id: int, title: str, body: str, data: dict = None):
    rider = await Rider.get_or_none(id=rider_id)
    token = getattr(rider, "fcm_token", None)

    if not rider or not token:
        logger.warning("Rider %s has no FCM token (or rider missing); skipping push", rider_id)
        return False

    try:
        # Build APNS payload correctly. Prefer class constructors but fall back to dict if not available.
        try:
            # preferred: use ApsAlert / Aps classes if present
            aps_alert = messaging.ApsAlert(title=title, body=body)
            aps = messaging.Aps(alert=aps_alert, badge=1, sound="default")
            apns_payload = messaging.APNSPayload(aps=aps)
            apns_config = messaging.APNSConfig(payload=apns_payload)
        except AttributeError:
            # fallback: older/newer firebase-admin might not expose those helper classes
            apns_payload = messaging.APNSPayload(
                aps={
                    "alert": {"title": title, "body": body},
                    "badge": 1,
                    "sound": "default",
                }
            )
            apns_config = messaging.APNSConfig(payload=apns_payload)

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=token,
            android=messaging.AndroidConfig(priority="high"),
            apns=apns_config,
        )

        # messaging.send is blocking — run it in a threadpool so we don't block the event loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, messaging.send, message)
        logger.info("Push sent to rider %s: %s", rider_id, response)
        return True

    except Exception as exc:
        logger.exception("Failed to send push to rider %s: %s", rider_id, exc)
        return False
