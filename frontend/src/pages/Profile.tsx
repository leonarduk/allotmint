import React from "react";

export default function ProfilePage() {
  const user = {
    name: "Jane Doe",
    email: "jane@example.com",
    avatar: "https://via.placeholder.com/150",
  };

  return (
    <div style={{ textAlign: "center" }}>
      <img
        src={user.avatar}
        alt={user.name}
        style={{ borderRadius: "50%", width: 150, height: 150 }}
      />
      <h1>{user.name}</h1>
      <p>{user.email}</p>

      import { useUser } from "../UserContext";
import { useConfig } from "../ConfigContext";

export default function Profile() {
  const { profile } = useUser();
  const { theme } = useConfig();

  if (!profile) {
    return <div>No profile loaded.</div>;
  }

  return (
    <div style={{ padding: "1rem" }}>
      {profile.picture && (
        <img
          src={profile.picture}
          alt={profile.name}
          style={{ width: "80px", borderRadius: "50%" }}
        />
      )}
      <h2>{profile.name}</h2>
      <p>{profile.email}</p>
      <p>Preferred theme: {theme}</p>
    </div>
  );
}
