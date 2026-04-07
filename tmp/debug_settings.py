from backend.config import get_settings
import os

def check_keys():
    settings = get_settings()
    keys_to_check = [
        "api_football_key",
        "odds_api_key",
        "gemini_api_key",
        "anthropic_api_key",
        "deepseek_api_key",
        "telegram_bot_token",
        "telegram_chat_id",
        "sendgrid_api_key"
    ]
    
    print("--- Settings Diagnosis ---")
    print(f"Current Working Directory: {os.getcwd()}")
    print(f".env file exists: {os.path.exists('.env')}")
    
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            lines = f.readlines()
            print(f".env line count: {len(lines)}")
            # Print first few chars of each key found (masked)
            for line in lines:
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if v:
                        print(f"Found in .env: {k}={v[:3]}***")
                    else:
                        print(f"Found in .env: {k}=[EMPTY]")

    print("\n--- Effective Settings ---")
    for key in keys_to_check:
        val = getattr(settings, key, None)
        status = "[SET]" if val and len(val) > 0 else "[EMPTY]"
        if val and len(val) > 0:
            print(f"{key:20}: {status} ({val[:3]}...)")
        else:
            print(f"{key:20}: {status}")

if __name__ == "__main__":
    check_keys()
