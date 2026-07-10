import { create } from "zustand";
import type { Company, InsightFeature } from "../types";

type AppState = {
  userId?: string;
  accountName?: string;
  selectedCompany?: Company;
  selectedFeature: InsightFeature;
  currentJobId?: string;
  login: (account: { userId: string; accountName: string }) => void;
  logout: () => void;
  setSelectedCompany: (company?: Company) => void;
  setSelectedFeature: (feature: InsightFeature) => void;
  setCurrentJobId: (jobId?: string) => void;
};

const getInitialAccount = () => {
  const raw = localStorage.getItem("ant-secretariat-account");
  if (!raw) return {};
  try {
    return JSON.parse(raw) as { userId?: string; accountName?: string };
  } catch {
    return {};
  }
};

const initialAccount = getInitialAccount();

export const useAppStore = create<AppState>((set) => ({
  userId: initialAccount.userId,
  accountName: initialAccount.accountName,
  selectedFeature: "price",
  login: (account) => {
    localStorage.setItem("ant-secretariat-account", JSON.stringify(account));
    set({ userId: account.userId, accountName: account.accountName });
  },
  logout: () => {
    localStorage.removeItem("ant-secretariat-account");
    set({ userId: undefined, accountName: undefined, selectedCompany: undefined, currentJobId: undefined });
  },
  setSelectedCompany: (selectedCompany) => set({ selectedCompany }),
  setSelectedFeature: (selectedFeature) => set({ selectedFeature }),
  setCurrentJobId: (currentJobId) => set({ currentJobId }),
}));
