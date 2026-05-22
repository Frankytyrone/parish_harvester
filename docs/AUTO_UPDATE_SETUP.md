# Brave auto-update setup for Parish Trainer

This guide is for Franky. Keep it simple. Follow each step in order.

## 1) What this gives you

- You install the extension once, then future updates install automatically.
- No Chrome Web Store account. No developer fee.
- Every tagged release can ship to Brave from this repo.

## 2) One-time machine setup (about 10 minutes)

> **Very important:** the `key` in `extension/manifest.json` keeps the extension ID stable.  
> If the `key` changes or is removed, Brave treats updates as a different extension and your saved extension data can be lost.

1. Open a terminal on your computer.
2. Go to your local repo folder.
3. Generate a private key file:

   ```bash
   openssl genrsa 2048 > key.pem
   ```

4. Convert that private key to base64 (single line):

   ```bash
   base64 key.pem | tr -d '\n'
   ```

5. Copy that long output string.
6. Open this exact GitHub page:  
   `https://github.com/Frankytyrone/parish_harvester/settings/secrets/actions`
7. Click **New repository secret**.
8. Name: `EXTENSION_PRIVATE_KEY`
9. Value: paste the base64 string from step 5.
10. Click **Add secret**.

![step1](images/auto-update-step1.png)

11. Back in terminal, get the public key string for `manifest.json`:

   ```bash
   openssl rsa -in key.pem -pubout -outform DER | base64 | tr -d '\n'
   ```

12. Open `/tmp/workspace/Frankytyrone/parish_harvester/extension/manifest.json`.
13. Find the top-level `"key"` field.
14. Replace `PASTE_BASE64_DER_PUBLIC_KEY_HERE` with the public key string from step 11.
15. Save the file.
16. Commit and push:

   ```bash
   git add extension/manifest.json
   git commit -m "chore: add extension public key for stable ID"
   git push origin main
   ```

![step2](images/auto-update-step2.png)

## 3) Cut your first release

1. Run:

   ```bash
   node scripts/bump-version.mjs patch
   ```

2. Run the printed commands.
3. Wait around 2 minutes for the workflow.
4. Open Releases: `https://github.com/Frankytyrone/parish_harvester/releases`
5. Confirm a new release exists and has a `.crx` file.

![step3](images/auto-update-step3.png)

## 4) Install it once in Brave

1. Open `brave://extensions`.
2. Turn on **Developer mode**.
3. Open your release page and download the `.crx` file.
4. Drag the `.crx` file onto `brave://extensions`.
5. Approve install.
6. Copy the Extension ID shown on the card.
7. Open `updates.xml` in this repo and confirm `<app appid='...'>` matches that ID.

![step4](images/auto-update-step4.png)

## 5) From now on — how updates work

1. Bump version with the script.
2. Commit.
3. Tag and push tags.
4. Workflow builds signed `.crx`, creates release, updates `updates.xml`.
5. Brave checks every ~5 hours and installs updates automatically.
6. To force now: open `brave://extensions` and click **Update**.

## 6) Troubleshooting

### Brave says `CRX_REQUIRED_PROOF_MISSING`

1. Make sure workflow used `EXTENSION_PRIVATE_KEY` secret.
2. Make sure the release `.crx` was built by workflow, not zipped by hand.
3. Re-run release from **Actions** with the same version/tag only after fixing secret.

### Extension ID changed after update

This means the `key` field in `manifest.json` was changed, empty, or removed.

1. Put the same public key back in `manifest.json` `"key"`.
2. Commit and push.
3. Bump version and release again.
4. Reinstall once if Brave already switched IDs.

### Workflow failed: tag vs manifest mismatch

1. Open `extension/manifest.json` and check `"version"`.
2. Your git tag must match exactly: `vX.Y.Z`.
3. Fix by editing version or creating the correct tag.

### Update does not seem to install

1. Check latest release has `.crx`.
2. Open `https://raw.githubusercontent.com/Frankytyrone/parish_harvester/main/updates.xml` and confirm version/codebase look correct.
3. In Brave, open `brave://extensions/?errors=`.
4. Click **Update** on `brave://extensions`.

![step5](images/auto-update-step5.png)

## 7) Honest caveats

- First install is manual. Future installs are automatic.
- Brave update checks are about every 5 hours, not instant.
- If Brave ever stops supporting self-hosted CRX updates, use an in-extension "click to update" fallback.

---

## Security note (read this)

Your `key.pem` must NEVER be committed to the repo. Only the public `key` field goes into `manifest.json`; the private key lives in the GitHub repo secret.
