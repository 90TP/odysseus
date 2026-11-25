# 7th Heaven Meals — Android

Native Android client for the existing 7th Heaven/Tandoor backend.

## Current features

- Jetpack Compose app shell
- Bottom navigation: Recipes, Calendar, Aerith, Shopping, Menu
- Recipe grid with backend images
- Recipe detail view with ingredients/instructions
- Configurable backend URL
- Optional bearer-token support
- LAN/Tailscale-friendly cleartext HTTP support for private network use

Calendar, Aerith and Shopping currently have native screen shells ready for their backend endpoint wiring.

## Default backend

The app currently defaults to:

`http://192.168.0.153:8321/`

Change this from **Menu & Settings** if the service address differs or you want to use a Tailscale/reverse-proxy URL.

## Build

Open `android/7th-heaven-meals` in Android Studio, allow Gradle sync, then run the `app` configuration.

From a machine with Android SDK/JDK 17 and Gradle installed:

```bash
gradle :app:assembleDebug
```

The debug APK will be produced under:

`app/build/outputs/apk/debug/app-debug.apk`

## Backend assumptions

The first implementation targets Tandoor-compatible recipe endpoints:

- `GET /api/recipe/`
- `GET /api/recipe/{id}/`
- recipe media paths such as `/media/recipes/...`

The client deliberately keeps backend construction in `data/Api.kt` so meal planning, shopping and Aerith endpoints can be added without changing the UI architecture.

## Next wiring pass

1. Confirm the exact recipe endpoint payload from the running Highwind instance and adjust the response adapter if needed.
2. Wire Calendar to the current meal-plan API.
3. Wire Shopping to the current shopping-list API.
4. Add Aerith planner/chat API calls.
5. Add offline cache and background refresh after the live API surface is stable.
