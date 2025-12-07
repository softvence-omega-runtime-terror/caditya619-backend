

import firebase_admin
from firebase_admin import credentials, messaging

cred = credentials.Certificate('app/quiklerider-firebase-sdk.json')
firebase_admin.initialize_app(cred)
print(f"Firebase initialized {firebase_admin.get_app().name}")
