import { CapacitorConfig } from '@capacitor/cli';

// warn if push notification key is missing to avoid runtime failures
const vapidPublicKey = process.env.VITE_VAPID_PUBLIC_KEY ?? '';
if (!vapidPublicKey) {
  console.warn(
    'VITE_VAPID_PUBLIC_KEY is not set; push notifications may not work.'
  );
}

const config: CapacitorConfig = {
  appId: 'com.allotmint.app',
  appName: 'AllotMint',
  webDir: '../frontend/dist',
  bundledWebRuntime: false,
  server: {
    androidScheme: 'https'
  },
  plugins: {
    PushNotifications: {
      presentationOptions: ['badge', 'sound', 'alert']
    }
  },
  extra: {
    vapidPublicKey
  }
};

export default config;
