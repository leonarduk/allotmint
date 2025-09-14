import React, { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  rootMargin?: string;
}

export default function Defer({ children, rootMargin = "0px" }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (visible) return;
    const el = ref.current;
    if (!el) return;
    if (!("IntersectionObserver" in window)) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [visible, rootMargin]);

  return <div ref={ref}>{visible ? children : null}</div>;
}
