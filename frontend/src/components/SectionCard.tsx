import { useState } from "react";
import { useTranslation } from "react-i18next";
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
  emptyMessage,
  defaultOpen = false,
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);
  const isEmpty = Array.isArray(items) && items.length === 0;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CollapsibleTrigger className="ml-2 text-sm" aria-label={open ? t("sectionCard.collapse") : t("sectionCard.expand")}>
            {open ? "−" : "+"}
          </CollapsibleTrigger>
        </CardHeader>
        <CollapsibleContent>
          <CardContent>
            {children}
            {isEmpty && (
              <p className="mt-2 text-sm text-muted-foreground">{emptyMessage === undefined ? t("sectionCard.noItems") : emptyMessage}</p>
            )}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  );
}
