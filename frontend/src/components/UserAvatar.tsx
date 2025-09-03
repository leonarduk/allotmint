import { Link } from "react-router-dom";
import { useAuth } from "../AuthContext";

export default function UserAvatar() {
  const { user } = useAuth();
  const content = user?.picture ? (
    <img
      src={user.picture}
      alt={user.name || user.email || "user avatar"}
      className="h-8 w-8 rounded-full"
    />
  ) : (
    <span role="img" aria-label="user avatar">
      👤
    </span>
  );
  return (
    <Link to="/profile" className="ml-4 cursor-pointer hover:opacity-80">
      {content}
    </Link>
  );
}

