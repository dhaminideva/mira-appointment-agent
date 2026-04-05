"""
test_email.py - Test SendGrid email directly
python test_email.py
"""
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

async def test():
    key = os.getenv("SENDGRID_API_KEY","")
    from_email = os.getenv("SENDGRID_FROM_EMAIL","")
    demo_email = os.getenv("DEMO_EMAIL","")
    print(f"API Key: {key[:20]}...")
    print(f"From: {from_email}")
    print(f"Demo email: {demo_email}")
    print()

    if not key or not from_email or not demo_email:
        print("MISSING — check your .env has:")
        print("SENDGRID_API_KEY=SG.xxx")
        print("SENDGRID_FROM_EMAIL=verified@email.com")
        print("DEMO_EMAIL=where_to_send@email.com")
        return

    from tools.email_sender import send_claim_email
    result = await send_claim_email(
        to_email=demo_email,
        first_name="Sarah",
        claim_status="approved",
        summary="Sarah Mitchell called to check her claim status. The claim was confirmed as approved and payment details were provided.",
        lang="en"
    )
    print(f"Result: {'SUCCESS' if result else 'FAILED'}")
    if result:
        print(f"Check {demo_email} for the email!")

asyncio.run(test())
