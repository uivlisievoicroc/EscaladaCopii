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

## Build notes

- Open this folder in Android Studio
- Use Android Studio's embedded JDK / Android SDK
- Sync the Gradle project and build the `app` module

This workspace does not currently have Java or Gradle installed, so the project was created but not compiled here.
