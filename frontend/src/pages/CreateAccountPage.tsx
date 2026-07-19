import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { requestAccountSignup } from "../api";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function SuccessView() {
  return (
    <div style={{ maxWidth: 480, margin: "2rem auto", padding: "1rem" }}>
      <h1>Request received</h1>
      <p role="status">
        Thanks — your request has been received and is pending admin
        approval. You will be contacted once your account has been set up.
      </p>
      <Link to="/" aria-label="Back to login">
        Back to login
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
  return (
    <div style={{ maxWidth: 480, margin: "2rem auto", padding: "1rem" }}>
      <h1>Create account</h1>
      <p>
        Request access to AllotMint. An administrator will review your
        request and set up your account.
      </p>
      <form onSubmit={onSubmit} noValidate>
        {error && (
          <div role="alert" aria-live="assertive" style={{ color: "red", marginBottom: "1rem" }}>
            {error}
          </div>
        )}
        <div style={{ marginBottom: "1rem" }}>
          <label htmlFor="create-account-name">Full name</label>
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
          <label htmlFor="create-account-email">Email</label>
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
            What would you like to use AllotMint for? (optional)
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
          {submitting ? "Submitting…" : "Request account"}
        </button>
      </form>
      <p style={{ marginTop: "1rem" }}>
        <Link to="/" aria-label="Back to login">
          Back to login
        </Link>
      </p>
    </div>
  );
}

export default function CreateAccountPage() {
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
      setError("Please enter your name and email address.");
      return;
    }
    if (!EMAIL_PATTERN.test(trimmedEmail)) {
      setError("Please enter a valid email address.");
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
      setError("Something went wrong submitting your request. Please try again.");
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
