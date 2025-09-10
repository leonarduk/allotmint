import { useEffect, useRef, useState } from 'react';

const SESSION_SECONDS = 25 * 60;
const BREAK_SECONDS = 5 * 60;

function notify(message: string) {
  if ('Notification' in window) {
    if (Notification.permission === 'granted') {
      new Notification(message);
    } else if (Notification.permission !== 'denied') {
      Notification.requestPermission().then((p) => {
        if (p === 'granted') new Notification(message);
      });
    }
  }
}

export default function PomodoroTimer() {
  const [seconds, setSeconds] = useState(SESSION_SECONDS);
  const [running, setRunning] = useState(false);
  const [onBreak, setOnBreak] = useState(false);
  const intervalRef = useRef<number>();

  useEffect(() => {
    if (!running) return;
    intervalRef.current = window.setInterval(() => {
      setSeconds((s) => s - 1);
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [running]);

  useEffect(() => {
    if (seconds >= 0) return;
    const nextBreak = !onBreak;
    notify(
      nextBreak
        ? 'Session complete! Time for a break.'
        : 'Break over! Back to focus.',
    );
    setOnBreak(nextBreak);
    setSeconds(nextBreak ? BREAK_SECONDS : SESSION_SECONDS);
  }, [seconds, onBreak]);

  const start = () => setRunning(true);
  const pause = () => setRunning(false);
  const reset = () => {
    setRunning(false);
    setOnBreak(false);
    setSeconds(SESSION_SECONDS);
  };

  const mins = Math.floor(seconds / 60)
    .toString()
    .padStart(2, '0');
  const secs = (seconds % 60).toString().padStart(2, '0');

  return (
    <div className="flex flex-col items-center">
      <div className="text-2xl font-mono mb-2">
        {mins}:{secs}
      </div>
      <div className="space-x-2">
        <button
          type="button"
          onClick={start}
          disabled={running}
          className="px-2 py-1 border rounded"
        >
          Start
        </button>
        <button
          type="button"
          onClick={pause}
          disabled={!running}
          className="px-2 py-1 border rounded"
        >
          Pause
        </button>
        <button
          type="button"
          onClick={reset}
          className="px-2 py-1 border rounded"
        >
          Reset
        </button>
      </div>
    </div>
  );
}

