import { ButtonLink, PageTitle } from "../components/ui";

export function NotFound() {
  return (
    <PageTitle title="Page not found" sub="This address doesn't match any screen."
      actions={<ButtonLink to="/" variant="primary">Go to overview</ButtonLink>} />
  );
}
