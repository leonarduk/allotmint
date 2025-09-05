import { Link } from "react-router-dom";
import { useAuth } from "../AuthContext";
export default function UserAvatar() {
  const { user } = useAuth();
  const placeholder =
    "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y&s=64";

  const content = user?.picture ? (
    <img
      src={user.picture}
      alt={user.name || user.email || "user avatar"}
      width={32}
      height={32}
      className="h-8 w-8 rounded-full"
    />
  ) : (
    <img
      src={placeholder}
      width={32}
      height={32}
      alt="user avatar"
      className="h-8 w-8 rounded-full"
    />
  );
  return (
    <Link to="/profile" className="ml-4 cursor-pointer hover:opacity-80">
      {content}
    </Link>
  );
}

