import { useEffect, useState } from 'react';

const SESSION_LENGTH = 25 * 60; // 25 minutes
const BREAK_LENGTH = 5 * 60; // 5 minutes

type Mode = 'session' | 'break';

function requestNotificationPermission() {
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }
}

function notify(message: string) {
  if ('Notification' in window && Notification.permission === 'granted') {
    new Notification(message);
  } else {
    alert(message);
  }
}

export default function PomodoroTimer() {
  const [seconds, setSeconds] = useState(SESSION_LENGTH);
  const [running, setRunning] = useState(false);
  const [mode, setMode] = useState<Mode>('session');

  useEffect(() => {
    requestNotificationPermission();
  }, []);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      setSeconds((s) => {
        if (s > 1) return s - 1;
        const nextMode: Mode = mode === 'session' ? 'break' : 'session';
        setMode(nextMode);
        notify(nextMode === 'break' ? 'Time for a break!' : 'Back to work!');
        return nextMode === 'session' ? SESSION_LENGTH : BREAK_LENGTH;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [running, mode]);

  const start = () => setRunning(true);
  const pause = () => setRunning(false);
  const reset = () => {
    setRunning(false);
    setMode('session');
    setSeconds(SESSION_LENGTH);
  };

  const minutes = String(Math.floor(seconds / 60)).padStart(2, '0');
  const secs = String(seconds % 60).padStart(2, '0');

  return (
    <div className="flex items-center gap-2">
      <span>{minutes}:{secs}</span>
      {running ? (
        <button onClick={pause}>Pause</button>
      ) : (
        <button onClick={start}>Start</button>
      )}
      <button onClick={reset}>Reset</button>
    </div>
  );
}

