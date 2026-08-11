import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import EmptyState from './EmptyState';

export default function DisabledFeature() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <EmptyState
      role="status"
      aria-live="polite"
      message={t(
        'app.featureDisabled',
        "This feature isn't enabled for this application."
      )}
      actions={[
        {
          label: t('app.returnHome', 'Return home'),
          onClick: () => navigate('/'),
        },
      ]}
    />
  );
}
