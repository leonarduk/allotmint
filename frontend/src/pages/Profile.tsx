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
    </div>
  );
}
