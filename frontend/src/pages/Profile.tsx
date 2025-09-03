import { useConfig } from "../ConfigContext";
import { useUser } from "../UserContext";

export default function ProfilePage() {
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

