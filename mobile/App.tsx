import React, { useState } from 'react';
import { Button, ScrollView, Text, TextInput, View } from 'react-native';

const API_BASE = process.env.EXPO_PUBLIC_API_BASE || 'http://localhost:8000';

export default function App() {
  const [idToken, setIdToken] = useState('');
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [owner, setOwner] = useState('');
  const [portfolio, setPortfolio] = useState<any | null>(null);

  async function handleLogin() {
    const res = await fetch(`${API_BASE}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id_token: idToken })
    });
    if (res.ok) {
      const data = await res.json();
      setAccessToken(data.access_token);
    }
  }

  async function loadPortfolio() {
    if (!accessToken || !owner) return;
    const res = await fetch(`${API_BASE}/portfolio/${owner}`, {
      headers: { Authorization: `Bearer ${accessToken}` }
    });
    if (res.ok) setPortfolio(await res.json());
  }

  if (!accessToken) {
    return (
      <View style={{ padding: 20 }}>
        <TextInput
          placeholder="ID Token"
          value={idToken}
          onChangeText={setIdToken}
          style={{ borderWidth: 1, marginBottom: 12, padding: 8 }}
        />
        <Button title="Login" onPress={handleLogin} />
      </View>
    );
  }

  return (
    <ScrollView style={{ padding: 20 }}>
      <TextInput
        placeholder="Owner"
        value={owner}
        onChangeText={setOwner}
        style={{ borderWidth: 1, marginBottom: 12, padding: 8 }}
      />
      <Button title="Load Portfolio" onPress={loadPortfolio} />
      {portfolio && <Text>{JSON.stringify(portfolio)}</Text>}
    </ScrollView>
  );
}

