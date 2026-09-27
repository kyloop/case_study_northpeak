import { expect, test } from "vitest";
import { isInvalidFilter, matchesFilter } from "./filters";

test("plain text is a case-insensitive contains", () => {
  expect(matchesFilter("Cascade Technologies", null, "cascade")).toBe(true);
  expect(matchesFilter("Cascade Technologies", null, "tech")).toBe(true);
  expect(matchesFilter("Cascade Technologies", null, "ferncrest")).toBe(false);
});

test("= is an exact match and != is not-equal, both case-insensitive", () => {
  expect(matchesFilter("Connector", null, "=connector")).toBe(true);
  expect(matchesFilter("Connector", null, "=Conn")).toBe(false);
  expect(matchesFilter("Connector", null, "!=Connector")).toBe(false);
  expect(matchesFilter("Enclosure", null, "!=Connector")).toBe(true);
});

test("numeric operators compare the raw number", () => {
  expect(matchesFilter("43.8", 43.77, ">40")).toBe(true);
  expect(matchesFilter("43.8", 43.77, ">=43.77")).toBe(true);
  expect(matchesFilter("43.8", 43.77, "<40")).toBe(false);
  expect(matchesFilter("43.8", 43.77, "<=43.8")).toBe(true);
  expect(matchesFilter("Connector", null, ">5")).toBe(false); // text column has no number
});

test("an empty or invalid filter matches everything and is flagged as invalid", () => {
  expect(matchesFilter("x", null, "   ")).toBe(true);
  expect(matchesFilter("x", 1, ">abc")).toBe(true);
  expect(isInvalidFilter(">abc")).toBe(true);
  expect(isInvalidFilter(">")).toBe(true);
  expect(isInvalidFilter(">5")).toBe(false);
  expect(isInvalidFilter("abc")).toBe(false);
});

test("on a numeric column a plain number means equals, not contains", () => {
  expect(matchesFilter("5", 5, "5")).toBe(true);
  expect(matchesFilter("25", 25, "5")).toBe(false);
  expect(matchesFilter("35", 35, "5")).toBe(false);
  expect(matchesFilter("5.5", 5.5, "5")).toBe(false);
  expect(matchesFilter("5.000", 5, "5")).toBe(true);        // same number
  expect(matchesFilter("5", 5, "5.0")).toBe(true);
  expect(matchesFilter("43.8", 43.77, "43.8")).toBe(true);   // matches what the cell displays
  expect(matchesFilter("3.945", 3.945, "3.9")).toBe(false);
});

test("=n and !=n also compare as numbers on numeric columns", () => {
  expect(matchesFilter("5", 5, "=5")).toBe(true);
  expect(matchesFilter("25", 25, "=5")).toBe(false);
  expect(matchesFilter("5", 5, "!=5")).toBe(false);
  expect(matchesFilter("25", 25, "!=5")).toBe(true);
});

test("on a numeric column, text that is not a number uses the text rules; blank cells never equal a number", () => {
  expect(matchesFilter("25", 25, "2")).toBe(false);          // 2 is a number: equals, so 25 no longer matches
  expect(matchesFilter("(blank)", null, "5")).toBe(false);
  expect(matchesFilter("abc", null, "ab")).toBe(true);       // a text column: contains, as before
  expect(matchesFilter("", 0, "0")).toBe(false);             // an empty cell shows nothing, so it is not 0
});
