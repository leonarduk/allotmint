import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

/**
 * Defers rendering of children until the wrapper enters the viewport.
 */
export default function Defer({ children }: Props) {
  const [visible, setVisible] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (visible) return;
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        setVisible(true);
        observer.disconnect();
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, [visible]);

  return <div ref={ref}>{visible ? children : null}</div>;
}
