import type { Holding } from '../data/adapter';

// Helper to convert string to number safely
function toNum(s: string | undefined | null): number {
  if (!s || s === '') return 0;
  const n = Number(s);
  return Number.isNaN(n) ? 0 : n;
}

// Helper to parse percentage strings
function toPercent(s: string | undefined | null): number {
  if (!s || s === '') return 0;
  const cleaned = String(s).replace(/%/g, '').trim();
  const n = Number(cleaned);
  return Number.isNaN(n) ? 0 : n;
}

// Create a key to match holdings across periods
// Uses company_name + investment_type + maturity_date as unique identifier
export function getHoldingKey(h: Holding): string {
  const name = (h.company_name || '').trim().toLowerCase();
  const type = (h.investment_type || '').trim().toLowerCase();
  const maturity = (h.maturity_date || '').trim();
  return `${name}::${type}::${maturity}`;
}

// Diff change types
export type ChangeType = 'added' | 'removed' | 'modified' | 'unchanged';

export type HoldingChange = {
  key: string;
  type: ChangeType;
  before: Holding | null;
  after: Holding | null;
  changes: {
    field: string;
    before: string | number;
    after: string | number;
    delta?: number;
    deltaPercent?: number;
  }[];
};

// Calculate diff between two periods
export function calculateDiff(
  beforeHoldings: Holding[],
  afterHoldings: Holding[]
): HoldingChange[] {
  const beforeMap = new Map<string, Holding>();
  const afterMap = new Map<string, Holding>();
  
  // Index holdings by key
  beforeHoldings.forEach(h => {
    const key = getHoldingKey(h);
    beforeMap.set(key, h);
  });
  
  afterHoldings.forEach(h => {
    const key = getHoldingKey(h);
    afterMap.set(key, h);
  });
  
  const allKeys = new Set([...beforeMap.keys(), ...afterMap.keys()]);
  const changes: HoldingChange[] = [];
  
  allKeys.forEach(key => {
    const before = beforeMap.get(key) || null;
    const after = afterMap.get(key) || null;
    
    if (!before && after) {
      // Added
      changes.push({
        key,
        type: 'added',
        before: null,
        after,
        changes: [],
      });
    } else if (before && !after) {
      // Removed
      changes.push({
        key,
        type: 'removed',
        before,
        after: null,
        changes: [],
      });
    } else if (before && after) {
      // Modified or unchanged
      const fieldChanges = compareHoldingFields(before, after);
      changes.push({
        key,
        type: fieldChanges.length > 0 ? 'modified' : 'unchanged',
        before,
        after,
        changes: fieldChanges,
      });
    }
  });
  
  return changes.sort((a, b) => {
    // Sort: added first, then removed, then modified, then unchanged
    const order = { added: 0, removed: 1, modified: 2, unchanged: 3 };
    if (order[a.type] !== order[b.type]) {
      return order[a.type] - order[b.type];
    }
    // Within same type, sort by company name
    const aName = (a.after?.company_name || a.before?.company_name || '').toLowerCase();
    const bName = (b.after?.company_name || b.before?.company_name || '').toLowerCase();
    return aName.localeCompare(bName);
  });
}

// Compare fields between two holdings
function compareHoldingFields(before: Holding, after: Holding): HoldingChange['changes'] {
  const changes: HoldingChange['changes'] = [];
  
  // Fields to compare
  const fields: Array<{
    key: keyof Holding;
    isNumeric: boolean;
    isPercent?: boolean;
  }> = [
    { key: 'company_name', isNumeric: false },
    { key: 'industry', isNumeric: false },
    { key: 'investment_type', isNumeric: false },
    { key: 'principal_amount', isNumeric: true },
    { key: 'amortized_cost', isNumeric: true },
    { key: 'cost', isNumeric: true },
    { key: 'fair_value', isNumeric: true },
    { key: 'interest_rate', isNumeric: true, isPercent: true },
    { key: 'spread', isNumeric: true, isPercent: true },
    { key: 'floor_rate', isNumeric: true, isPercent: true },
    { key: 'pik_rate', isNumeric: true, isPercent: true },
    { key: 'acquisition_date', isNumeric: false },
    { key: 'maturity_date', isNumeric: false },
    { key: 'reference_rate', isNumeric: false },
  ];
  
  fields.forEach(({ key, isNumeric, isPercent }) => {
    const beforeVal = before[key];
    const afterVal = after[key];
    
    if (isNumeric) {
      const beforeNum = isPercent ? toPercent(beforeVal) : toNum(beforeVal);
      const afterNum = isPercent ? toPercent(afterVal) : toNum(afterVal);
      
      if (Math.abs(beforeNum - afterNum) > 0.01) { // Threshold for numeric changes
        const delta = afterNum - beforeNum;
        const deltaPercent = beforeNum !== 0 ? (delta / beforeNum) * 100 : 0;
        
        changes.push({
          field: key,
          before: beforeNum,
          after: afterNum,
          delta,
          deltaPercent,
        });
      }
    } else {
      // String comparison
      const beforeStr = String(beforeVal || '').trim();
      const afterStr = String(afterVal || '').trim();
      
      if (beforeStr !== afterStr) {
        changes.push({
          field: key,
          before: beforeStr,
          after: afterStr,
        });
      }
    }
  });
  
  return changes;
}

// Summary statistics for a diff
export type DiffSummary = {
  added: { count: number; fairValue: number; cost: number; principal: number };
  removed: { count: number; fairValue: number; cost: number; principal: number };
  modified: { count: number; fairValueDelta: number; costDelta: number; principalDelta: number };
  unchanged: { count: number };
  totalBefore: { count: number; fairValue: number; cost: number; principal: number };
  totalAfter: { count: number; fairValue: number; cost: number; principal: number };
};

export function getDiffSummary(changes: HoldingChange[]): DiffSummary {
  const summary: DiffSummary = {
    added: { count: 0, fairValue: 0, cost: 0, principal: 0 },
    removed: { count: 0, fairValue: 0, cost: 0, principal: 0 },
    modified: { count: 0, fairValueDelta: 0, costDelta: 0, principalDelta: 0 },
    unchanged: { count: 0 },
    totalBefore: { count: 0, fairValue: 0, cost: 0, principal: 0 },
    totalAfter: { count: 0, fairValue: 0, cost: 0, principal: 0 },
  };
  
  changes.forEach(change => {
    if (change.type === 'added' && change.after) {
      summary.added.count++;
      summary.added.fairValue += toNum(change.after.fair_value);
      summary.added.cost += toNum(change.after.cost || change.after.amortized_cost);
      summary.added.principal += toNum(change.after.principal_amount);
      
      summary.totalAfter.count++;
      summary.totalAfter.fairValue += toNum(change.after.fair_value);
      summary.totalAfter.cost += toNum(change.after.cost || change.after.amortized_cost);
      summary.totalAfter.principal += toNum(change.after.principal_amount);
    } else if (change.type === 'removed' && change.before) {
      summary.removed.count++;
      summary.removed.fairValue += toNum(change.before.fair_value);
      summary.removed.cost += toNum(change.before.cost || change.before.amortized_cost);
      summary.removed.principal += toNum(change.before.principal_amount);
      
      summary.totalBefore.count++;
      summary.totalBefore.fairValue += toNum(change.before.fair_value);
      summary.totalBefore.cost += toNum(change.before.cost || change.before.amortized_cost);
      summary.totalBefore.principal += toNum(change.before.principal_amount);
    } else if (change.type === 'modified' && change.before && change.after) {
      summary.modified.count++;
      
      const beforeFV = toNum(change.before.fair_value);
      const afterFV = toNum(change.after.fair_value);
      summary.modified.fairValueDelta += (afterFV - beforeFV);
      
      const beforeCost = toNum(change.before.cost || change.before.amortized_cost);
      const afterCost = toNum(change.after.cost || change.after.amortized_cost);
      summary.modified.costDelta += (afterCost - beforeCost);
      
      const beforePrincipal = toNum(change.before.principal_amount);
      const afterPrincipal = toNum(change.after.principal_amount);
      summary.modified.principalDelta += (afterPrincipal - beforePrincipal);
      
      summary.totalBefore.count++;
      summary.totalBefore.fairValue += beforeFV;
      summary.totalBefore.cost += beforeCost;
      summary.totalBefore.principal += beforePrincipal;
      
      summary.totalAfter.count++;
      summary.totalAfter.fairValue += afterFV;
      summary.totalAfter.cost += afterCost;
      summary.totalAfter.principal += afterPrincipal;
    } else if (change.type === 'unchanged' && change.before && change.after) {
      summary.unchanged.count++;
      
      summary.totalBefore.count++;
      summary.totalBefore.fairValue += toNum(change.before.fair_value);
      summary.totalBefore.cost += toNum(change.before.cost || change.before.amortized_cost);
      summary.totalBefore.principal += toNum(change.before.principal_amount);
      
      summary.totalAfter.count++;
      summary.totalAfter.fairValue += toNum(change.after.fair_value);
      summary.totalAfter.cost += toNum(change.after.cost || change.after.amortized_cost);
      summary.totalAfter.principal += toNum(change.after.principal_amount);
    }
  });
  
  return summary;
}









