import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../AuthContext";
export default function UserAvatar() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const placeholder =
    "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y&s=64";

  const content = user?.picture ? (
    <img
      src={user.picture}
      alt={user.name || user.email || t("userAvatar.alt")}
      width={32}
      height={32}
      className="h-8 w-8 rounded-full"
    />
  ) : (
    <img
      src={placeholder}
      width={32}
      height={32}
      alt={t("userAvatar.alt")}
      className="h-8 w-8 rounded-full"
    />
  );
  return (
    <Link to="/settings" className="ml-4 cursor-pointer hover:opacity-80">
      {content}
    </Link>
  );
}

