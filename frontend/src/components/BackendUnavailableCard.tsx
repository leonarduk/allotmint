interface Props {
  onRetry?: () => void;
}

export default function BackendUnavailableCard({ onRetry }: Props) {
  return (
    <div className="mx-auto my-8 max-w-[400px] rounded-lg border border-gray-300 p-4 text-center">
      <h2>Backend unavailable</h2>
      <p className="mb-4 text-gray-600">
        The backend service could not be reached. You can retry or open a
        cached read-only view.
      </p>
      <div className="mb-4">
        <button onClick={onRetry} disabled={!onRetry}>
          Retry
        </button>
      </div>
      <div className="text-sm">
        <a
          href="/snapshots/index.html"
          target="_blank"
          rel="noopener noreferrer"
          className="mr-2"
        >
          Cached view
        </a>
        <a
          href="/offline"
          target="_blank"
          rel="noopener noreferrer"
        >
          Read-only mode
        </a>
      </div>
    </div>
  );
}
