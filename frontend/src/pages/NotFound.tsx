import { ButtonLink, PageTitle } from "../components/ui";
import { useTitle } from "../lib/useTitle";

export function NotFound() {
  useTitle("Page not found");
  return (
    <PageTitle title="Page not found" sub="This address doesn't match any screen."
      actions={<ButtonLink to="/" variant="primary">Go to overview</ButtonLink>} />
  );
}
