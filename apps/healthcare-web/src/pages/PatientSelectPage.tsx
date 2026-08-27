import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Forbidden } from "../components/Forbidden";
import { PatientLookupPanel } from "../patient/PatientLookupPanel";
import { LOOKUP_WORKSPACES, lookupPurposeForWorkspace } from "../patient/purpose";
import { canOpenWorkspace, hasPermission, type WorkspaceId } from "../tenant/permissions";
import { useTenant } from "../tenant/TenantContext";

export function PatientSelectPage() {
  const { t } = useTranslation();
  const { effectivePermissions, selectedOrganization } = useTenant();
  const canLookup = hasPermission(effectivePermissions, "mpi.identity.read");
  const workflows = useMemo(
    () => LOOKUP_WORKSPACES.filter((workspace) => canOpenWorkspace(effectivePermissions, workspace)),
    [effectivePermissions],
  );
  const [chosenWorkspace, setChosenWorkspace] = useState<WorkspaceId | null>(null);
  const workspace =
    workflows.length === 1
      ? workflows[0]
      : chosenWorkspace && workflows.includes(chosenWorkspace)
        ? chosenWorkspace
        : null;
  const purpose = workspace ? lookupPurposeForWorkspace(workspace) : null;
  const panelKey = `${selectedOrganization?.organization_id ?? "none"}:${workspace ?? "none"}`;

  if (!canLookup) {
    return <Forbidden title={t("errors.forbiddenTitle")} body={t("errors.forbiddenBody")} />;
  }

  return (
    <section>
      <h1>{t("patient.selectTitle")}</h1>
      <p>{t("patient.selectBody")}</p>
      {workflows.length > 1 ? (
        <fieldset className="field">
          <legend>{t("patient.workflow")}</legend>
          {workflows.map((item) => (
            <label key={item}>
              <input
                type="radio"
                name="patient-lookup-workflow"
                value={item}
                checked={workspace === item}
                onChange={() => setChosenWorkspace(item)}
              />
              {t(`nav.${item}`)}
            </label>
          ))}
        </fieldset>
      ) : null}
      {purpose ? (
        <PatientLookupPanel key={panelKey} purpose={purpose} />
      ) : (
        <p>{t(workflows.length ? "patient.chooseWorkflow" : "patient.noWorkflow")}</p>
      )}
    </section>
  );
}
