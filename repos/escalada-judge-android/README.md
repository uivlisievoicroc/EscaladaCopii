# Escalada Judge Remote Android

Native Android shell for `Judge Remote`.

## What it does

- Loads the existing web `Judge Remote` inside a `WebView`
- Intercepts Android `Vol+` and `Vol-`
- Injects the matching keyboard events into the page
- Keeps the screen awake during judging

## Current mapping

- `Vol+` -> `AudioVolumeUp` -> `+0.1 Hold`
- `Vol-` -> `AudioVolumeDown` -> `+1 Hold`

This matches the shortcut support already added in `escalada-ui`.

## Expected URL

Paste a normal judge URL, for example:

```text
http://192.168.1.50:8000/#/judge/0?cat=Seniori
```

If you paste only a host or IP, the app prefixes `http://`.

The app only accepts LAN/private judge hosts by default:

- private IPv4 ranges (`10.*`, `172.16.*`-`172.31.*`, `192.168.*`, `169.254.*`)
- `localhost`
- `.local` hostnames
- explicitly allowed hosts configured in `BuildConfig.ALLOWED_JUDGE_HOSTS`

Public domains and non-HTTP schemes are rejected before loading the WebView.

## Build notes

- Open this folder in Android Studio
- Use JDK 17 (Android Studio's embedded JDK is fine) and the Android SDK
- Sync the Gradle project and build the `app` module

This workspace does not currently have Java or Gradle installed, so the project was created but not compiled here.
