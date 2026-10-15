import { useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { createReportTemplate } from "@/api/reports";
import { ReportBuilder } from "@/components/ReportBuilder";
import { buildTemplatePayload } from "@/components/ReportBuilder/sections";
import type { ReportTemplateInput, ReportTemplateMetadata } from "@/types";

/** Router state /reports reads to confirm a save and select the new template. */
export interface ReportsLocationState {
  createdTemplate?: Pick<ReportTemplateMetadata, "template_id" | "name">;
}

export default function ReportTemplateCreator() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const created = useRef<ReportsLocationState["createdTemplate"]>(undefined);

  // ReportBuilder calls this after a successful save as well as on Close, so
  // a save is reported back to /reports through router state.
  const handleCancel = useCallback(() => {
    if (created.current) {
      const state: ReportsLocationState = { createdTemplate: created.current };
      navigate("/reports", { state });
    } else {
      navigate("/reports");
    }
  }, [navigate]);

  // Errors propagate to ReportBuilder, which shows them and stays open (#10914).
  const handleCreate = useCallback(
    async (input: ReportTemplateInput) => {
      const payload = buildTemplatePayload(input, (option) => t(option.labelKey));
      const saved = await createReportTemplate(payload);
      created.current = { template_id: saved.template_id, name: saved.name };
    },
    [t],
  );

  return <ReportBuilder onCreate={handleCreate} onCancel={handleCancel} />;
}
