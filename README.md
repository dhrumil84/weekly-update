# Weekly Weather Email

Sends a 7-day forecast for **Anaheim, CA** to `patel.dhrumil@protonmail.com` every **Sunday at 9pm Pacific**, rendered as a clean HTML email with weather icons, highs/lows (°F with °C in parens), and max wind speed (mph). Data from [Open-Meteo](https://open-meteo.com) (free, no API key).

## Files

- `weather_email.py` — fetch + render + send (stdlib only, no dependencies)
- `.github/workflows/weekly-weather.yml` — Sunday 9pm Pacific cron
- `.env.example` — template for local testing

## Setup

### 1. Create a Gmail App Password

1. Enable 2-Step Verification: https://myaccount.google.com/security
2. Generate an App Password: https://myaccount.google.com/apppasswords
   - App name: `weather-email` → **Create**
3. Copy the 16-character password. Google shows it **once** — if you lose it, just generate a new one and revoke the old.

### 2. Add it as a GitHub Actions Secret (for production)

In your GitHub repo:
- `Settings` → `Secrets and variables` → `Actions` → `New repository secret`
- Name: `SMTP_PASSWORD`
- Value: the 16-char app password (no spaces)

That's the only secret you need. `SMTP_USER` and `RECIPIENT_EMAIL` are hardcoded in the workflow.

### 3. (Optional) Local testing

```powershell
copy .env.example .env
# edit .env, paste the app password
```

Then in PowerShell:

```powershell
$env:SMTP_USER       = "dhrumil84@gmail.com"
$env:SMTP_PASSWORD   = "your-app-password"
$env:RECIPIENT_EMAIL = "patel.dhrumil@protonmail.com"

# Preview the HTML without sending
python weather_email.py --dry-run
start preview.html

# Actually send a test email (bypasses the Sunday-9pm guard)
python weather_email.py --force
```

> **Never commit `.env`.** It's gitignored. The plaintext password lives only on your machine and in GitHub Secrets (encrypted).

### 4. Push and verify

After pushing to GitHub:
- Go to `Actions` → `Weekly Weather Email` → `Run workflow` (manual trigger). This sends immediately so you can confirm it works end-to-end.
- After that, it runs automatically every Sunday 9pm Pacific.

## How the scheduling works

GitHub Actions cron is **UTC-only** and does not observe DST. Sun 9pm Pacific is:

- Mon 04:00 UTC during **PDT** (mid-March → early November)
- Mon 05:00 UTC during **PST** (early November → mid-March)

The workflow schedules **both** times. The script then checks: "is it actually Sunday 8–10pm in America/Los_Angeles right now?" Only one of the two runs will pass the check, so you get exactly one email per week with no manual DST adjustments.

## Customizing

- **Location:** edit `LATITUDE`, `LONGITUDE`, `LOCATION_NAME` at the top of `weather_email.py`.
- **Units:** Open-Meteo params `temperature_unit` and `wind_speed_unit` in `fetch_forecast()`.
- **Send time:** change the two cron lines in the workflow and the `is_target_time()` window.
