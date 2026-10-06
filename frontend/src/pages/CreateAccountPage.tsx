import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { requestAccountSignup } from "../api";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function SuccessView() {
  const { t } = useTranslation();
  return (
    <div style={{ maxWidth: 480, margin: "2rem auto", padding: "1rem" }}>
      <h1>{t("createAccount.receivedTitle")}</h1>
      <p role="status">
        {t("createAccount.receivedMessage")}
      </p>
      <Link to="/" aria-label={t("createAccount.backToLogin")}>
        {t("createAccount.backToLogin")}
      </Link>
    </div>
  );
}

interface CreateAccountFormProps {
  name: string;
  email: string;
  note: string;
  error: string | null;
  submitting: boolean;
  onNameChange: (value: string) => void;
  onEmailChange: (value: string) => void;
  onNoteChange: (value: string) => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
}

function CreateAccountForm({
  name,
  email,
  note,
  error,
  submitting,
  onNameChange,
  onEmailChange,
  onNoteChange,
  onSubmit,
}: CreateAccountFormProps) {
  const { t } = useTranslation();
  return (
    <div style={{ maxWidth: 480, margin: "2rem auto", padding: "1rem" }}>
      <h1>{t("createAccount.title")}</h1>
      <p>
        {t("createAccount.intro")}
      </p>
      <form onSubmit={onSubmit} noValidate>
        {error && (
          <div role="alert" aria-live="assertive" style={{ color: "red", marginBottom: "1rem" }}>
            {error}
          </div>
        )}
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="create-account-name">{t("createAccount.fullName")}</label>
          <br />
          <input
            id="create-account-name"
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            required
            style={{ width: "100%" }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="create-account-email">{t("createAccount.email")}</label>
          <br />
          <input
            id="create-account-email"
            type="email"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            required
            style={{ width: "100%" }}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="create-account-note">
            {t("createAccount.noteLabel")}
          </label>
          <br />
          <textarea
            id="create-account-note"
            value={note}
            onChange={(e) => onNoteChange(e.target.value)}
            rows={3}
            style={{ width: "100%" }}
          />
        </div>
        <button type="submit" disabled={submitting}>
          {submitting ? t("createAccount.submitting") : t("createAccount.requestAccount")}
        </button>
      </form>
      <p style={{ marginTop: "1rem" }}>
        <Link to="/" aria-label={t("createAccount.backToLogin")}>
          {t("createAccount.backToLogin")}
        </Link>
      </p>
    </div>
  );
}

export default function CreateAccountPage() {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    const trimmedName = name.trim();
    const trimmedEmail = email.trim();

    if (!trimmedName || !trimmedEmail) {
      setError(t("createAccount.nameEmailRequired"));
      return;
    }
    if (!EMAIL_PATTERN.test(trimmedEmail)) {
      setError(t("createAccount.invalidEmail"));
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await requestAccountSignup({
        name: trimmedName,
        email: trimmedEmail,
        note: note.trim() || undefined,
      });
      setSubmitted(true);
    } catch (err) {
      const status = (err as Record<string, unknown> | null)?.status;
      if (typeof status === "number") {
        console.error(
          `Failed to submit account signup request (HTTP ${status})`,
          err,
        );
      } else {
        console.error("Failed to submit account signup request", err);
      }
      setError(t("createAccount.submitFailed"));
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return <SuccessView />;
  }

  function handleNameChange(value: string) {
    setName(value);
    setError(null);
  }

  function handleEmailChange(value: string) {
    setEmail(value);
    setError(null);
  }

  function handleNoteChange(value: string) {
    setNote(value);
    setError(null);
  }

  return (
    <CreateAccountForm
      name={name}
      email={email}
      note={note}
      error={error}
      submitting={submitting}
      onNameChange={handleNameChange}
      onEmailChange={handleEmailChange}
      onNoteChange={handleNoteChange}
      onSubmit={handleSubmit}
    />
  );
}
