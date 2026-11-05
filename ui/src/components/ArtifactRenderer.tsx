import type { ArtifactInfo } from "../api/types";
import { AdaptiveCardArtifactRenderer } from "./AdaptiveCardArtifactRenderer";

interface ArtifactRendererProps {
  artifact: ArtifactInfo;
  onSubmit?: (data: Record<string, unknown>) => Promise<void> | void;
  isSubmitting?: boolean;
}

export function ArtifactRenderer({
  artifact,
  onSubmit,
  isSubmitting = false,
}: ArtifactRendererProps) {
  return (
    <AdaptiveCardArtifactRenderer
      artifact={artifact}
      onSubmit={onSubmit}
      isSubmitting={isSubmitting}
    />
  );
}

export { AdaptiveCardArtifactRenderer };

