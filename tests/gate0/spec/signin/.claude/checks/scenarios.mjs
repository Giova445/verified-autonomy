import {
  ORDERS,
  clickSignOut,
  open,
  ordersPageShown,
  refusedAttempt,
  signIn,
  signInPageShown,
  signOutButtonShown,
  submit,
} from "./steps.mjs";

const wrongPassword = (account) => ({ ...account, password: `${account.password}-not-it` });
const unknownEmail = (account) => ({ ...account, email: `no-such-user-${account.email}` });
const rotated = (orders) => [...orders.slice(1), orders[0]];

const refusedInputs = (account) => [
  unknownEmail(account),
  { email: "", password: "" },
  { email: account.email, password: "" },
  { email: "", password: account.password },
];

const signedOutEverywhere = () => [
  ...signInPageShown(),
  open("/orders"),
  ...signInPageShown(),
];

export const scenarios = {
  "signed-out": {
    target: "/",
    check: () => signedOutEverywhere(),
    controls: (account) => [
      {
        name: "the visitor is already signed in",
        steps: [...signIn(account), open("/"), ...signedOutEverywhere()],
      },
    ],
  },
  "orders-after-sign-in": {
    target: "/login",
    check: (account) => [...submit(account), ...ordersPageShown(account)],
    controls: (account) => [
      {
        name: "the password is wrong",
        steps: [...submit(wrongPassword(account)), ...ordersPageShown(account)],
      },
      {
        name: "another user's email is expected",
        steps: [
          ...submit(account),
          ...ordersPageShown({ email: `someone-else-${account.email}` }),
        ],
      },
      {
        name: "the orders are expected in another order",
        steps: [...submit(account), ...ordersPageShown(account, rotated(ORDERS))],
      },
      {
        name: "a fourth order is expected",
        steps: [...submit(account), ...ordersPageShown(account, ORDERS, ORDERS.length + 1)],
      },
    ],
  },
  "wrong-password": {
    target: "/login",
    check: (account) => refusedAttempt(wrongPassword(account)),
    controls: (account) => [
      { name: "the password is right", steps: refusedAttempt(account) },
    ],
  },
  "unknown-email-or-empty-fields": {
    target: "/login",
    check: (account) => refusedInputs(account).flatMap(refusedAttempt),
    controls: (account) => [
      { name: "the email and password are right", steps: refusedAttempt(account) },
    ],
  },
  "reload-keeps-sign-in": {
    target: "/login",
    check: (account) => [
      ...signIn(account),
      open("/orders"),
      ...ordersPageShown(account),
    ],
    controls: (account) => [
      {
        name: "the user never signed in, as when a reload loses the session",
        steps: [
          ...signIn(wrongPassword(account)),
          open("/orders"),
          ...ordersPageShown(account),
        ],
      },
    ],
  },
  "sign-out": {
    target: "/login",
    check: (account) => [
      ...signIn(account),
      signOutButtonShown(),
      clickSignOut(),
      ...signedOutEverywhere(),
    ],
    controls: (account) => [
      {
        name: "Sign out is never used, as when it does nothing",
        steps: [...signIn(account), signOutButtonShown(), ...signedOutEverywhere()],
      },
      {
        name: "there is no Sign out button, as when the user never signed in",
        steps: [
          ...signIn(wrongPassword(account)),
          signOutButtonShown(),
          clickSignOut(),
          ...signedOutEverywhere(),
        ],
      },
    ],
  },
};
