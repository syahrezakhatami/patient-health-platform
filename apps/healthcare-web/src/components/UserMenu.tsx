import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { useTenant } from "../tenant/TenantContext";
import { confirmDiscardUnsavedWork, hasUnsavedWork } from "../tenant/unsavedWork";

export function UserMenu() {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const { user } = useTenant();
  const label = user?.display_name || t("session.unknownUser");

  return (
    <div className="user-menu">
      <span>
        {t("session.user")} <strong>{label}</strong>
      </span>
      <button
        type="button"
        className="button danger"
        onClick={() => {
          if (!hasUnsavedWork()) {
            void logout();
            return;
          }
          void confirmDiscardUnsavedWork("logout").then((ok) => {
            if (ok) {
              void logout();
            }
          });
        }}
      >
        {t("auth.signOut")}
      </button>
    </div>
  );
}
