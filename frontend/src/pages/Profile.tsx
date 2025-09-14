import { useConfig } from "../ConfigContext";
import { useAuth } from "../AuthContext";
import EmptyState from "../components/EmptyState";
export default function ProfilePage() {
  const { user } = useAuth();
  const { theme } = useConfig();

  if (!user) {
    return <EmptyState message="No user information available." />;
  }

  const placeholder =
    "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y&s=192";

  return (
    <div className="flex flex-col items-center space-y-4 p-4">
      <h1 className="text-2xl">Profile</h1>
      {user.picture ? (
        <img
          src={user.picture}
          alt={user.name || user.email || "user avatar"}
          width={96}
          height={96}
          className="h-24 w-24 rounded-full"
        />
      ) : (
        <img
          src={placeholder}
          width={96}
          height={96}
          alt="user avatar"
          className="h-24 w-24 rounded-full"
        />
      )}
      {user.name && <div className="text-xl">{user.name}</div>}
      {user.email && (
        <div className="text-gray-800 dark:text-gray-200">{user.email}</div>
      )}
      <p className="text-gray-800 dark:text-gray-200">
        Preferred theme: {theme}
      </p>
    </div>
  );
}

