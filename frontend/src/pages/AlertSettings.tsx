import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Menu from "../components/Menu";
import {
  getAlertThreshold,
  setAlertThreshold,
  savePushSubscription,
  deletePushSubscription,
} from "../api";
import { useUser } from "../UserContext";

export default function AlertSettings() {
  const { t } = useTranslation();
  const { profile } = useUser();
  // Owner is determined from the authenticated user's profile
  const owner = profile?.email;
  const [threshold, setThreshold] = useState<number | "">("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  const [pushSupported, setPushSupported] = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushStatus, setPushStatus] = useState<
    "idle" | "enabled" | "disabled" | "denied" | "error"
  >("idle");

  useEffect(() => {
    if (!owner) {
      setThreshold("");
      return;
    }
    getAlertThreshold(owner)
      .then((r) => setThreshold(r.threshold))
      .catch(() => setThreshold(""));
  }, [owner]);

  useEffect(() => {
    if (
      typeof navigator !== "undefined" &&
      "serviceWorker" in navigator &&
      "PushManager" in window
    ) {
      setPushSupported(true);
      navigator.serviceWorker.ready
        .then((reg) => reg.pushManager.getSubscription())
        .then((sub) => setPushEnabled(!!sub))
        .catch(() => {
          /* ignore */
        });
    }
  }, []);

  function urlBase64ToUint8Array(base64String: string) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  async function enablePush() {
    if (!owner) return;
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setPushStatus("denied");
        return;
      }
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: import.meta.env.VITE_VAPID_PUBLIC_KEY
          ? urlBase64ToUint8Array(import.meta.env.VITE_VAPID_PUBLIC_KEY as string)
          : undefined,
      });
      await savePushSubscription(
        owner,
        sub.toJSON() as import("../api").PushSubscriptionJSON,
      );
      setPushEnabled(true);
      setPushStatus("enabled");
    } catch {
      setPushStatus("error");
    }
  }

  async function disablePush() {
    if (!owner) return;
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) await sub.unsubscribe();
      await deletePushSubscription(owner);
      setPushEnabled(false);
      setPushStatus("disabled");
    } catch {
      setPushStatus("error");
    }
  }

  async function save() {
    if (threshold === "" || !owner) return;
    setStatus("saving");
    try {
      await setAlertThreshold(owner, Number(threshold));
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: "0 auto", padding: "1rem" }}>
      <Menu />
      <h1>{t("alertSettings.title")}</h1>
      <p>{t("alertSettings.description")}</p>
      <div style={{ marginTop: "1rem" }}>
        <label>
          {t("alertSettings.threshold")}{" "}
          <input
            type="number"
            value={threshold}
            onChange={(e) =>
              setThreshold(e.target.value === "" ? "" : Number(e.target.value))
            }
            style={{ width: "4rem" }}
          />
        </label>
        <button onClick={save} style={{ marginLeft: "0.5rem" }}>
          {t("alertSettings.save")}
        </button>
        {status === "saved" && (
          <span style={{ marginLeft: "0.5rem" }}>
            {t("alertSettings.status.saved")}
          </span>
        )}
        {status === "error" && (
          <span style={{ marginLeft: "0.5rem" }}>
            {t("alertSettings.status.error")}
          </span>
        )}
      </div>
      <div style={{ marginTop: "2rem" }}>
        <h2>{t("alertSettings.push.title")}</h2>
        {!pushSupported ? (
          <p>{t("alertSettings.push.notSupported")}</p>
        ) : (
          <div>
            <button
              onClick={pushEnabled ? disablePush : enablePush}
              style={{ marginTop: "0.5rem" }}
              disabled={!owner}
            >
              {pushEnabled
                ? t("alertSettings.push.disable")
                : t("alertSettings.push.enable")}
            </button>
            {pushStatus === "denied" && (
              <p>{t("alertSettings.push.denied")}</p>
            )}
            {pushStatus === "error" && (
              <p>{t("alertSettings.push.error")}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
