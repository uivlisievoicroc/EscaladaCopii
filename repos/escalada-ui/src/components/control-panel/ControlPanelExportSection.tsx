import React, { FC } from 'react';
import type { Box } from '../../types';
import AdminExportOfficialView from '../AdminExportOfficialView';

type Props = {
  disabled: boolean;
  listboxes: Box[];
  exportBoxId: number;
  onChangeExportBoxId: (value: number) => void;
  onExport: () => Promise<void> | void;
};

const ControlPanelExportSection: FC<Props> = ({
  disabled,
  listboxes,
  exportBoxId,
  onChangeExportBoxId,
  onExport,
}) => (
  <AdminExportOfficialView
    disabled={disabled}
    listboxes={listboxes}
    exportBoxId={exportBoxId}
    onChangeExportBoxId={onChangeExportBoxId}
    onExport={onExport}
  />
);

export default ControlPanelExportSection;
