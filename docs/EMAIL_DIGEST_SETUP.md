# Email Digest Setup (Bulletin of the Week)

If you want a weekly email when bulletins update, follow these 6 steps:

1. Open repository secrets:  
   https://github.com/Frankytyrone/parish_harvester/settings/secrets/actions
2. Add these six secrets exactly:
   - `SMTP_SERVER`
   - `SMTP_PORT`
   - `SMTP_USERNAME`
   - `SMTP_PASSWORD`
   - `DIGEST_FROM`
   - `DIGEST_TO`
3. Choose one email provider setup:
   - **Gmail (easy):** use `smtp.gmail.com`, port `587`, your Gmail address as username, and a Gmail **App Password** as `SMTP_PASSWORD`.
   - **SendGrid (free tier):** use `smtp.sendgrid.net`, port `587`, username `apikey`, and your SendGrid API key as `SMTP_PASSWORD`.
4. Set `DIGEST_FROM` to the sender email (must match your provider/account rules).
5. Set `DIGEST_TO` to the recipient address (or multiple comma-separated addresses).
6. In Actions, run **Bulletin Email Digest** manually once (`workflow_dispatch`) to confirm delivery.

Honest caveat: if you skip this setup, nothing breaks — the workflow just exits cleanly with a warning.
