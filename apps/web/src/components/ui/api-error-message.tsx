import type { ApiClientError } from "@/lib/api/request-api";
import { presentApiClientError } from "@/lib/api/client-error-message";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert";

type ApiErrorMessageProps = {
  error: ApiClientError;
};

export function ApiErrorMessage({ error }: ApiErrorMessageProps) {
  const { title, detail, requestId, fieldErrors } =
    presentApiClientError(error);

  return (
    <Alert variant="destructive" className="mt-5">
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>
        <p>{detail}</p>
        {fieldErrors && fieldErrors.length > 0 ? (
          <ul className="mt-3 list-disc pl-5">
            {fieldErrors.map((field) => (
              <li key={`${field.pointer}:${field.detail}`}>
                <span className="mr-1.5 font-mono">{field.pointer}</span>
                {field.detail}
              </li>
            ))}
          </ul>
        ) : null}
        {requestId ? (
          <p className="mt-3 text-xs opacity-80">参照 ID: {requestId}</p>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
