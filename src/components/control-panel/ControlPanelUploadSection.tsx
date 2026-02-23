import React, { FC } from 'react';
import ModalUpload from '../ModalUpload';

type Props = {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (file: File, category: string, routesCount?: number, holdsCounts?: number[]) => void;
};

const ControlPanelUploadSection: FC<Props> = ({ isOpen, onClose, onUpload }) => (
  <div className="space-y-4">
    <div className="grid grid-cols-[repeat(1,minmax(320px,560px))] gap-3">
      <ModalUpload isOpen={isOpen} embedded onClose={onClose} onUpload={onUpload} />
    </div>
  </div>
);

export default ControlPanelUploadSection;
