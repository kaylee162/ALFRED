from calendar_tools.calendar_service import get_calendar_service
from gmail_tools.gmail_service import get_gmail_service


def authenticate_google() -> None:
    print("Starting Google authentication...")
    print("A browser window should open.")

    calendar_service = get_calendar_service()
    calendar_service.calendarList().list(maxResults=1).execute()
    print("Calendar authentication successful.")

    gmail_service = get_gmail_service()
    gmail_service.users().getProfile(userId="me").execute()
    print("Gmail authentication successful.")

    print("Google authentication complete.")
    print("A new shared token.json should now exist in backend/.")


if __name__ == "__main__":
    authenticate_google()