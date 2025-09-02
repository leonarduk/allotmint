import { useAuth } from "../AuthContext";

export default function ProfilePage() {
  const { user } = useAuth();
  if (!user) {
    return <div className="p-4">No user information available.</div>;
  }
  return (
    <div className="flex flex-col items-center space-y-4 p-4">
      <h1 className="text-2xl">Profile</h1>
      {user.picture && (
        <img
          src={user.picture}
          alt={user.name || user.email || "user avatar"}
          className="h-24 w-24 rounded-full"
        />
      )}
      {user.name && <div className="text-xl">{user.name}</div>}
      {user.email && <div className="text-gray-600">{user.email}</div>}
    </div>
  );
}
