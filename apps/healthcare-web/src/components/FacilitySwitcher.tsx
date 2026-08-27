import { useTranslation } from "react-i18next";

import { useTenant } from "../tenant/TenantContext";

export function FacilitySwitcher() {
  const { t } = useTranslation();
  const {
    accessibleFacilities,
    workFacilityId,
    selectWorkFacility,
    facilityScope,
    phase,
  } = useTenant();

  if (phase !== "ready") {
    return null;
  }
  if (facilityScope === "ALL_IN_ORGANIZATION" && accessibleFacilities.length === 0) {
    return null;
  }
  if (accessibleFacilities.length === 0) {
    return null;
  }

  return (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor="facility-switcher">{t("facility.switch")}</label>
      <select
        id="facility-switcher"
        value={workFacilityId ?? ""}
        onChange={(event) => {
          void selectWorkFacility(event.target.value || null);
        }}
      >
        {facilityScope === "ALL_IN_ORGANIZATION" || !workFacilityId ? (
          <option value="">{t("facility.unset")}</option>
        ) : null}
        {accessibleFacilities.map((facility) => (
          <option key={facility.id} value={facility.id}>
            {facility.name}
          </option>
        ))}
      </select>
    </div>
  );
}
