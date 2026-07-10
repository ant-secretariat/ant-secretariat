import { create } from "zustand";
import type { Company, InsightFeature } from "../types";

type AppState = {
  userId: string;
  selectedCompany?: Company;
  selectedFeature: InsightFeature;
  currentJobId?: string;
  setUserId: (userId: string) => void;
  setSelectedCompany: (company?: Company) => void;
  setSelectedFeature: (feature: InsightFeature) => void;
  setCurrentJobId: (jobId?: string) => void;
};

const getInitialUserId = () => {
  const stored = localStorage.getItem("ant-secretariat-user-id");
  if (stored) return stored;
  const generated = crypto.randomUUID();
  localStorage.setItem("ant-secretariat-user-id", generated);
  return generated;
};

export const useAppStore = create<AppState>((set) => ({
  userId: getInitialUserId(),
  selectedFeature: "price",
  setUserId: (userId) => {
    localStorage.setItem("ant-secretariat-user-id", userId);
    set({ userId });
  },
  setSelectedCompany: (selectedCompany) => set({ selectedCompany }),
  setSelectedFeature: (selectedFeature) => set({ selectedFeature }),
  setCurrentJobId: (currentJobId) => set({ currentJobId }),
}));
