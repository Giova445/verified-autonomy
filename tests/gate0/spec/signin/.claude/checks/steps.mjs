export const ORDERS = [
  "#2001 Standing desk $480",
  "#2002 Desk mat $35",
  "#2003 Webcam $120",
];

const ORDER_INFORMATION = "text=/#\\d{4}|Standing desk|Desk mat|Webcam|\\$\\d/";
const ALERT_TEXT = "Wrong email or password";
const EMAIL_FIELD = 'role=textbox[name="Email"]';
const PASSWORD_FIELD = 'role=textbox[name="Password"]';
const SIGN_IN_BUTTON = 'role=button[name="Sign in"]';
const SIGN_OUT_BUTTON = 'role=button[name="Sign out"]';
const HEADING = "role=heading";

export const open = (path) => ({ goto: path });

const GATE_TIMEOUT_MS = 300;

const gate = (selector) => [
  { visible: selector },
  { waitFor: selector, timeout: GATE_TIMEOUT_MS },
];

export const submit = ({ email, password }) => [
  open("/login"),
  { fill: { selector: EMAIL_FIELD, value: email } },
  { fill: { selector: PASSWORD_FIELD, value: password } },
  { click: SIGN_IN_BUTTON },
];

export const signIn = (credentials) => [
  ...submit(credentials),
  { url: { equals: "/orders" } },
];

export const signOutButtonShown = () => ({ visible: SIGN_OUT_BUTTON });

export const clickSignOut = () => ({ click: SIGN_OUT_BUTTON });

export const signInPageShown = () => [
  { url: { contains: "/login" } },
  ...gate('role=heading[name="Sign in"]'),
  { text: { selector: HEADING, equals: "Sign in" } },
  { visible: EMAIL_FIELD },
  { visible: PASSWORD_FIELD },
  { visible: SIGN_IN_BUTTON },
  { count: { selector: ORDER_INFORMATION, equals: 0 } },
];

export const alertShown = () => [
  ...gate("role=alert"),
  { text: { selector: "role=alert", equals: ALERT_TEXT } },
];

export const ordersPageShown = ({ email }, orders = ORDERS, rows = orders.length) => [
  { url: { equals: "/orders" } },
  ...gate('role=heading[name="Your orders"]'),
  { text: { selector: HEADING, equals: "Your orders" } },
  { text: { selector: "text=Signed in as", contains: `Signed in as ${email}` } },
  { count: { selector: "role=listitem", equals: rows } },
  ...orders.map((order, index) => ({
    text: { selector: `role=listitem >> nth=${index}`, equals: order },
  })),
];

export const refusedAttempt = (credentials) => [
  ...submit(credentials),
  ...alertShown(),
  ...signInPageShown(),
  open("/orders"),
  ...signInPageShown(),
];
