import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import { ReportBuilder } from "@/components/ReportBuilder";
import type { ReportTemplateInput } from "@/types";

export default function ReportTemplateCreator() {
  const navigate = useNavigate();

  const handleCancel = useCallback(() => {
    navigate("/reports");
  }, [navigate]);

  const handleCreate = useCallback(async (_input: ReportTemplateInput) => {
    console.info("Report template creation is not persisted in preview mode.");
  }, []);

  return <ReportBuilder onCreate={handleCreate} onCancel={handleCancel} />;
}
