import type {
  AccessibleFacilitiesResponse,
  StaffContextResponse,
  StaffOrganizationsResponse,
} from "../api/generated/iam-shell";

export const ORG_A = "11111111-1111-4111-8111-111111111111";
export const ORG_B = "22222222-2222-4222-8222-222222222222";
export const FAC_1 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1";
export const FAC_2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2";
export const USER_ID = "99999999-9999-4999-8999-999999999999";

export const clinicianPermissions = [
  "clinical.condition.read",
  "clinical.encounter.read",
  "mpi.identity.read",
];

export const registrarPermissions = [
  "clinical.encounter.create",
  "clinical.encounter.read",
  "mpi.identity.read",
];

export const identityPermissions = [
  "mpi.identity.read",
  "mpi.match.review",
  "mpi.merge.execute",
];

export const adminPermissions = [
  "iam.membership.manage",
  "org.facility.create",
  "org.identifier.manage",
];

export function org(id: string, name: string, roleCodes: string[]) {
  return {
    organization_id: id,
    name,
    code: name.slice(0, 8).toUpperCase(),
    organization_type: "HOSPITAL",
    status: "ACTIVE",
    role_codes: roleCodes,
  };
}

export function organizationsResponse(
  organizations: StaffOrganizationsResponse["organizations"],
  provisioned = true,
): StaffOrganizationsResponse {
  return {
    provisioned,
    user: {
      id: USER_ID,
      subject: "staff-user",
      display_name: "Staff User",
    },
    organizations,
  };
}

export function contextResponse(
  organizationId: string,
  name: string,
  permissions: string[],
  extras?: Partial<StaffContextResponse>,
): StaffContextResponse {
  const organization = extras?.organization ?? org(organizationId, name, extras?.role_codes ?? ["CLINICIAN"]);
  return {
    provisioned: true,
    user: {
      id: USER_ID,
      subject: "staff-user",
      display_name: "Staff User",
    },
    organization,
    role_codes: extras?.role_codes ?? organization.role_codes,
    effective_permissions: permissions,
    facility_scope: extras?.facility_scope ?? "ALL_IN_ORGANIZATION",
    work_facility_required: extras?.work_facility_required ?? false,
  };
}

export function facilitiesResponse(
  organizationId: string,
  extras?: Partial<AccessibleFacilitiesResponse>,
): AccessibleFacilitiesResponse {
  return {
    organization_id: organizationId,
    facility_scope: "ALL_IN_ORGANIZATION",
    facilities: [],
    ...extras,
  };
}
