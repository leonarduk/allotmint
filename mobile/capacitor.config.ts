import { CapacitorConfig } from '@capacitor/cli';

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
    vapidPublicKey: process.env.VITE_VAPID_PUBLIC_KEY
  }
};

export default config;
