import { useAuth } from "../AuthContext";

export default function UserAvatar() {
  const { user } = useAuth();
  if (user?.picture) {
    return (
      <img
        src={user.picture}
        alt={user.name || user.email || "user avatar"}
        style={{ width: 32, height: 32, borderRadius: "50%", marginLeft: "1rem" }}
      />
    );
  }
  return (
    <span role="img" aria-label="user avatar" style={{ marginLeft: "1rem" }}>
      👤
    </span>
  );
}

