import type { ArtifactInfo } from "../api/types";
import { A2UIArtifactRenderer } from "./A2UIArtifactRenderer";

interface ArtifactRendererProps {
  artifact: ArtifactInfo;
  onSubmit?: (data: Record<string, unknown>) => Promise<void> | void;
  onClickButton?: (buttonId: string, context: Record<string, unknown>) => Promise<void> | void;
  isSubmitting?: boolean;
  readOnly?: boolean;
}

export function ArtifactRenderer({
  artifact,
  onSubmit,
  onClickButton,
  isSubmitting = false,
  readOnly = false,
}: ArtifactRendererProps) {
  return (
    <A2UIArtifactRenderer
      artifact={artifact}
      onSubmit={onSubmit}
      onClickButton={onClickButton}
      isSubmitting={isSubmitting}
      readOnly={readOnly}
    />
  );
}

export { A2UIArtifactRenderer };
