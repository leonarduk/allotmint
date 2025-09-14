import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./ui/collapsible";

interface Props {
  title: React.ReactNode;
  children: React.ReactNode;
  items?: unknown[];
  emptyMessage?: React.ReactNode;
  defaultOpen?: boolean;
}

export default function SectionCard({
  title,
  children,
  items,
  emptyMessage = "No items.",
  defaultOpen = false,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const isEmpty = Array.isArray(items) && items.length === 0;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CollapsibleTrigger className="ml-2 text-sm" aria-label={open ? "Collapse" : "Expand"}>
            {open ? "−" : "+"}
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent>
            {children}
            {isEmpty && (
              <p className="mt-2 text-sm text-muted-foreground">{emptyMessage}</p>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
