import os
import sys
import asyncio
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession


class TelegramForwarder:
    def __init__(self, api_id, api_hash, phone_number=None, session_string=None):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.phone_number = phone_number

        # On a server we authenticate with a pre-generated StringSession so we
        # never need to type a login code. Locally we fall back to a session
        # file keyed by phone number.
        if session_string:
            session = StringSession(session_string)
        elif phone_number:
            session = f'session_{phone_number}'
        else:
            session = StringSession()

        self.client = TelegramClient(session, self.api_id, self.api_hash)

    async def ensure_login(self):
        await self.client.connect()

        if not await self.client.is_user_authorized():
            try:
                await self.client.send_code_request(self.phone_number)
                code = input("Enter login code: ")
                await self.client.sign_in(self.phone_number, code)

            except errors.SessionPasswordNeededError:
                pw = input("Enter 2FA Password: ")
                await self.client.sign_in(password=pw)

    async def list_chats(self):
        await self.ensure_login()
        dialogs = await self.client.get_dialogs()

        with open(f"chats_of_{self.phone_number}.txt", "w", encoding="utf-8") as f:
            for d in dialogs:
                line = f"Chat ID: {d.id}, Title: {d.title}"
                print(line)
                f.write(line + "\n")

        print("\n✅ Chats exported.\n")

    async def forward_messages_live(self, source_chat_id, destination_chat_id):
        """Forward ALL messages as-is (text + images + media)"""
        await self.ensure_login()

        print("\n🚀 Forwarder Started — Forwarding everything\n")

        # FIX INVALID PEER ISSUE
        try:
            destination_peer = await self.client.get_entity(destination_chat_id)
        except Exception as e:
            print("\n❌ Cannot resolve destination peer!")
            print("Make sure:")
            print("- You joined the channel/group")
            print("- You have permission to send")
            print("- ID is correct")
            print("Error:", e)
            return

        @self.client.on(events.NewMessage(chats=source_chat_id))
        async def handler(event):
            try:
                text = event.message.message or ""

                if event.message.photo or event.message.file:
                    # Image / photo / file with its original caption
                    await self.client.send_file(
                        destination_peer,
                        file=event.message.media,
                        caption=text if text else None
                    )
                    print("🖼️ Forwarded MEDIA")

                else:
                    # Text-only message
                    await self.client.send_message(destination_peer, text)
                    print("📤 Forwarded TEXT:", text)

            except Exception as e:
                print("❌ Error Forwarding:", e)

        # RUN FOREVER
        await self.client.run_until_disconnected()


# -------------------------------
# CREDENTIALS FUNCTIONS
# -------------------------------

def load_credentials():
    try:
        with open("credentials.txt", "r") as f:
            api_id = f.readline().strip()
            api_hash = f.readline().strip()
            phone = f.readline().strip()
        return api_id, api_hash, phone
    except:
        return None, None, None


def save_credentials(api_id, api_hash, phone):
    with open("credentials.txt", "w") as f:
        f.write(api_id + "\n" + api_hash + "\n" + phone)


# -------------------------------
# SESSION STRING GENERATOR (run locally once)
# -------------------------------

async def generate_session_string():
    """Run locally: logs in interactively and prints a SESSION_STRING to copy
    into Railway's environment variables."""
    api_id = os.environ.get("API_ID") or input("API ID: ")
    api_hash = os.environ.get("API_HASH") or input("API Hash: ")
    phone = os.environ.get("PHONE") or input("Phone number: ")

    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        try:
            await client.sign_in(phone, input("Enter login code: "))
        except errors.SessionPasswordNeededError:
            await client.sign_in(password=input("Enter 2FA Password: "))

    print("\n✅ Copy this SESSION_STRING into your Railway variables:\n")
    print(client.session.save())
    print()
    await client.disconnect()


# -------------------------------
# DEPLOY MODE (Railway / any server) — driven by env vars
# -------------------------------

async def run_from_env():
    api_id = os.environ["API_ID"]
    api_hash = os.environ["API_HASH"]
    session_string = os.environ["SESSION_STRING"]
    source = int(os.environ["SOURCE_CHAT_ID"])
    dest = int(os.environ["DEST_CHAT_ID"])

    bot = TelegramForwarder(api_id, api_hash, session_string=session_string)
    await bot.forward_messages_live(source, dest)


# -------------------------------
# MAIN PROGRAM
# -------------------------------

async def main():
    # `python TelegramForwarder.py login` -> generate a session string locally
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        await generate_session_string()
        return

    # If deploy env vars are present (e.g. on Railway), run automatically.
    if os.environ.get("SESSION_STRING") and os.environ.get("SOURCE_CHAT_ID"):
        await run_from_env()
        return

    # Otherwise: local interactive mode.
    api_id, api_hash, phone_number = load_credentials()

    if not api_id or not api_hash or not phone_number:
        api_id = input("API ID: ")
        api_hash = input("API Hash: ")
        phone_number = input("Phone number: ")
        save_credentials(api_id, api_hash, phone_number)

    bot = TelegramForwarder(api_id, api_hash, phone_number)

    print("\nChoose an option:")
    print("1. List Chats")
    print("2. Start Forwarding\n")
    choice = input("Your choice: ")

    if choice == "1":
        await bot.list_chats()

    elif choice == "2":
        source = int(input("Source Chat ID: "))
        dest = int(input("Destination Chat ID: "))

        await bot.forward_messages_live(source, dest)

    else:
        print("❌ Invalid choice.")


if __name__ == "__main__":
    asyncio.run(main())
